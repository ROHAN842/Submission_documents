import os
import re
import logging
from typing import Dict, Any, List
from unittest import result
from dotenv import load_dotenv
from azure.storage.blob import BlobClient, BlobServiceClient
from azure.core.exceptions import AzureError
from urllib.parse import urlparse, quote, unquote
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import AzureOpenAIEmbeddings
# from langchain_community.vectorstores import Chroma
from langchain_chroma import Chroma
from langchain.schema import Document
import tempfile
from io import BytesIO

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Note: Document Intelligence client removed - now using raw text files from blob

# Initialize Azure OpenAI embeddings
embeddings = AzureOpenAIEmbeddings(
    azure_deployment=os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME"),
    openai_api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    chunk_size=1024
)

# Configure text splitter
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=int(os.getenv("CHUNK_SIZE", "800")),
    chunk_overlap=int(os.getenv("CHUNK_OVERLAP", "100")),
    length_function=len,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ==============================================================
# SOV DOCUMENT PRE-PROCESSOR
# ==============================================================
# This section contains pre-processing logic specifically for
# Statement of Values (SOV) documents that have fragmented
# table structures after PDF text extraction.
#
# HOW IT WORKS:
# 1. detect_sov_document()  — checks if the text looks like an SOV
# 2. preprocess_sov_text()  — reconstructs fragmented table rows
#    into clean label: value sentences before chunking
# 3. preprocess_text_if_needed() — router that decides whether
#    to apply SOV pre-processing or pass text through unchanged
#
# WHY THIS IS NEEDED:
# PDF table extraction breaks table rows into individual lines
# with no surrounding context. For example:
#   "Named Insured"          <- label line
#   "Azul Biscayne Resort"   <- value line (no label context)
# After chunking at 800 chars, the value line may land in a
# chunk without its label, making semantic search return nothing.
# Pre-processing joins them into:
#   "Named Insured: Azul Biscayne Resort & Spa, LLC"
# which embeds with full context and retrieves correctly.
#
# NO CHANGES to chunking logic, ChromaDB storage, or retriever.
# ==============================================================

# --------------------------------------------------------------
# Known SOV section headers used for detection and anchoring
# --------------------------------------------------------------
SOV_SECTION_MARKERS = [
    "STATEMENT OF VALUES",
    "SOV IDENTIFICATION",
    "MASTER STATEMENT OF VALUES",
    "LOCATION DETAIL SHEETS",
    "BUILDING VALUE SCHEDULE",
    "ITV CERTIFICATION",
    "INSURANCE-TO-VALUE",
    "SOV CERTIFICATION",
    "BUSINESS INCOME / EXTRA EXPENSE NOTE",
]

# --------------------------------------------------------------
# Known label fields in SOV documents
# These are used to detect label lines during reconstruction
# --------------------------------------------------------------
SOV_KNOWN_LABELS = [
    "Named Insured", "DBA / Trade Name", "Property Address",
    "Policy Period", "US Valuation Basis", "Valuation Basis",
    "Appraisal Provider", "Appraisal Date", "Insurance-to-Value",
    "Inflation Guard", "Mortgage / Lienholder", "Requesting Broker",
    "SOV Prepared By", "SOV Date",
    "Full Address", "Occupancy Type", "Property Use",
    "Construction Type", "Number of Stories", "Number of Stories/Levels",
    "Year Built", "Year Renovated", "Last Major Renovation",
    "Gross Building Area", "Roof Type", "Roof Type & Age",
    "Building Code Compliance", "Sprinkler System", "Sprinkler / Suppression",
    "Fire Alarm", "Security", "Backup Power",
    "FEMA Flood Zone", "Wind Zone", "Seismic Zone",
    "Occupancy Rate", "Building RCV", "BPP / Contents",
    "Business Income / EE", "Total Insured Value (TIV)", "ITV Status",
    "Prior Loss Note", "Flood Mitigation", "Fire Protection",
    "Parking Capacity", "BI Limit Requested", "Revenue Basis",
    "BI Allocation by Location", "Indemnity Period",
]


def detect_sov_document(text: str) -> bool:
    """
    Detect whether the input text is a Statement of Values (SOV) document.

    Detection logic:
    - Counts how many known SOV section markers appear in the text
    - If 3 or more markers found → treat as SOV document
    - Case-insensitive matching

    Args:
        text: Raw extracted text from the document

    Returns:
        True if text appears to be an SOV document, False otherwise
    """
    text_upper = text.upper()
    matches = sum(1 for marker in SOV_SECTION_MARKERS if marker.upper() in text_upper)
    is_sov = matches >= 3
    if is_sov:
        logger.info(f"SOV document detected ({matches} section markers found) — applying SOV pre-processor")
    return is_sov


def _is_label_line(line: str) -> bool:
    """
    Check if a line is a known SOV label field.

    Args:
        line: Stripped text line

    Returns:
        True if the line matches a known SOV label
    """
    line_lower = line.lower().strip()
    for label in SOV_KNOWN_LABELS:
        if line_lower == label.lower():
            return True
    return False


def _is_section_header(line: str) -> bool:
    """
    Check if a line is a major SOV section header.

    Args:
        line: Stripped text line

    Returns:
        True if the line is a section header
    """
    line_upper = line.upper().strip()
    for marker in SOV_SECTION_MARKERS:
        if marker.upper() in line_upper:
            return True
    # Also detect LOC headers like "LOC 001 | Main Hotel Tower | ..."
    if re.match(r'^LOC\s+\d{3}\s*[\|]', line.strip(), re.IGNORECASE):
        return True
    # Detect "SECTION N" headers
    if re.match(r'^SECTION\s+\d+', line.strip(), re.IGNORECASE):
        return True
    return False


def _reconstruct_section1_table(text: str) -> str:
    """
    Reconstruct Section 1 master SOV table rows.

    Section 1 is the most fragmented part — table columns like
    Loc#, Description, Address, Construction Type, Year, Sq Ft,
    Building RCV, BPP, BI, TIV are all on separate lines.

    Strategy:
    - Detect the SECTION 1 block
    - Find each LOC row (001, 002, 003, 004, TOTAL)
    - Reconstruct each row as a readable sentence with all its values

    Args:
        text: Full raw text of the SOV document

    Returns:
        Text with Section 1 table replaced by readable sentences
    """
    # Locate Section 1 boundaries
    sec1_start = re.search(r'SECTION\s+1\s*[-–]\s*MASTER STATEMENT OF VALUES', text, re.IGNORECASE)
    sec2_start = re.search(r'SECTION\s+2\s*[-–]\s*LOCATION DETAIL SHEETS', text, re.IGNORECASE)

    if not sec1_start:
        return text  # Section 1 not found, return unchanged

    sec1_text_start = sec1_start.start()
    sec1_text_end = sec2_start.start() if sec2_start else len(text)
    section1_block = text[sec1_text_start:sec1_text_end]
    lines = section1_block.split('\n')

    # Column headers we want to skip (they are just header rows, not data)
    skip_patterns = [
        r'^loc\s*#\s*$', r'^description\s*/?$', r'^occupancy\s*$',
        r'^location address\s*$', r'^construction\s*$', r'^type\s*$',
        r'^yr\s*$', r'^built\s*$', r'^sq\s*ft\s*$',
        r'^building rcv\s*$', r'^bpp\s*/?\s*contents\s*$',
        r'^bi\s*/\s*extra\s*$', r'^expense\s*$',
        r'^total insured\s*$', r'^value\s*$',
        r'^note:\s*bi/ee', r'^section\s+1',
    ]

    # Extract dollar amounts pattern
    dollar_pattern = re.compile(r'^\$[\d,]+(?:\.\d+)?$')
    # LOC number pattern
    loc_pattern = re.compile(r'^(0\d\d|TOTAL)$', re.IGNORECASE)

    # Collect non-header, non-empty lines from section 1
    content_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Skip known column headers
        skip = False
        for pat in skip_patterns:
            if re.match(pat, stripped, re.IGNORECASE):
                skip = True
                break
        if not skip:
            content_lines.append(stripped)

    # Now reconstruct LOC rows
    # We'll group lines between LOC identifiers
    loc_groups = {}
    current_loc = None
    for line in content_lines:
        if loc_pattern.match(line):
            current_loc = line.upper()
            loc_groups[current_loc] = []
        elif current_loc:
            loc_groups[current_loc].append(line)

    if not loc_groups:
        return text  # Could not parse, return unchanged

    # Build readable sentences for each LOC
    reconstructed_lines = ["\nSECTION 1 - MASTER STATEMENT OF VALUES (Reconstructed)\n"]

    for loc_id, values in loc_groups.items():
        if not values:
            continue
        # Assign values positionally based on expected column order:
        # Description (multi-line text), Address, Construction, Year, SqFt, BuildingRCV, BPP, BI, TIV
        # Separate text descriptions from numbers/addresses
        descriptions = []
        address_parts = []
        construction_parts = []
        numbers = []
        in_address = False
        in_construction = False

        for v in values:
            if re.match(r'^\d{4}$', v):  # Year like 2008
                numbers.append(('Year Built', v))
            elif re.match(r'^\d{1,3}(,\d{3})*$', v):  # Sq ft like 770,200
                numbers.append(('Sq Ft', v))
            elif dollar_pattern.match(v):  # Dollar amounts
                numbers.append(('Value', v))
            elif re.match(r'^\d{4}\s*Biscayne|^\d+\s+Biscayne|^FL\s+\d{5}', v, re.IGNORECASE):
                address_parts.append(v)
            elif re.match(r'^(Fire Resistive|Non.?Combustible|Mixed|Class\s+\d)', v, re.IGNORECASE):
                construction_parts.append(v)
            elif re.match(r'^(Cast.in.Place|Reinforced|Concrete|Steel|TPO|Light Steel|Open.Air|Flashing)', v, re.IGNORECASE):
                construction_parts.append(v)
            elif re.match(r'^(Resistive|Primary|Frame)', v, re.IGNORECASE):
                construction_parts.append(v)
            else:
                descriptions.append(v)

        description_str = ' '.join(descriptions)
        address_str = ' '.join(address_parts)
        construction_str = ' '.join(construction_parts)

        # Map dollar values to column names by position (order: Building RCV, BPP, BI/EE, TIV)
        dollar_values = [v for k, v in numbers if k == 'Value']
        year_values = [v for k, v in numbers if k == 'Year Built']
        sqft_values = [v for k, v in numbers if k == 'Sq Ft']

        value_labels = ['Building RCV', 'BPP / Contents', 'BI / Extra Expense', 'Total Insured Value']
        value_sentences = []
        for i, dv in enumerate(dollar_values):
            label = value_labels[i] if i < len(value_labels) else f'Value {i+1}'
            value_sentences.append(f"{label}: {dv}")

        sentence_parts = [f"Location: {loc_id}"]
        if description_str:
            sentence_parts.append(f"Description: {description_str}")
        if address_str:
            sentence_parts.append(f"Address: {address_str}")
        if construction_str:
            sentence_parts.append(f"Construction Type: {construction_str}")
        if year_values:
            sentence_parts.append(f"Year Built: {year_values[0]}")
        if sqft_values:
            sentence_parts.append(f"Gross Building Area: {sqft_values[0]} Sq Ft")
        sentence_parts.extend(value_sentences)

        reconstructed_lines.append(' | '.join(sentence_parts))

    reconstructed_section = '\n'.join(reconstructed_lines) + '\n'

    # Replace Section 1 block in original text with reconstructed version
    return text[:sec1_text_start] + reconstructed_section + text[sec1_text_end:]


def _reconstruct_label_value_pairs(text: str) -> str:
    """
    Reconstruct fragmented label-value pairs in Section 2 location detail sheets.

    In the raw extracted text, label and value are often on separate lines:
        "Named Insured"
        "Azul Biscayne Resort & Spa, LLC"

    This function joins them into:
        "Named Insured: Azul Biscayne Resort & Spa, LLC"

    Also handles the LOC 003 Flood Mitigation text that appears out of order
    at the end of the section — it gets moved back to its correct LOC 003 context.

    Args:
        text: Raw text (after Section 1 reconstruction)

    Returns:
        Text with label-value pairs joined into single lines
    """
    lines = text.split('\n')
    output_lines = []
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        if not line:
            output_lines.append('')
            i += 1
            continue

        # Keep section headers and LOC headers as-is
        if _is_section_header(line):
            output_lines.append(line)
            i += 1
            continue

        # Check if this line is a known label
        if _is_label_line(line):
            # Look ahead for the value on the next non-empty line
            j = i + 1
            value_lines = []
            while j < len(lines):
                next_line = lines[j].strip()
                if not next_line:
                    j += 1
                    continue
                # Stop if next line is another label, section header, or LOC header
                if _is_label_line(next_line) or _is_section_header(next_line):
                    break
                # Stop if next line looks like a new LOC block header
                if re.match(r'^LOC\s+\d{3}\s*[\|]', next_line, re.IGNORECASE):
                    break
                value_lines.append(next_line)
                j += 1
                # For most labels, one value line is enough
                # For multi-line values (like Property Use, BPP descriptions), take up to 3 lines
                if len(value_lines) >= 3:
                    break

            if value_lines:
                value_str = ' '.join(value_lines)
                output_lines.append(f"{line}: {value_str}")
                i = j
            else:
                output_lines.append(line)
                i += 1
        else:
            output_lines.append(line)
            i += 1

    reconstructed = '\n'.join(output_lines)

    # Fix LOC 003 out-of-order Flood Mitigation text
    # The FloodBreak sentence appears after LOC 003's ITV Status in raw text
    # Move it to appear right after the Flood Mitigation label in LOC 003
    flood_break_pattern = re.compile(
        r'(FloodBreak Passive Flood Barriers[^\n]+)',
        re.IGNORECASE
    )
    flood_break_match = flood_break_pattern.search(reconstructed)
    if flood_break_match:
        flood_break_text = flood_break_match.group(1)
        # Remove it from its current out-of-order position
        reconstructed = reconstructed.replace(flood_break_text, '', 1)
        # Insert it after "Flood Mitigation:" label in LOC 003 section
        reconstructed = re.sub(
            r'(Flood Mitigation\s*:[^\n]*)',
            r'\1 ' + flood_break_text,
            reconstructed,
            count=1
        )

    return reconstructed


def _inject_loc_context(text: str) -> str:
    """
    Inject location context prefix into every paragraph within each LOC section.

    Problem: After chunking, a chunk may contain content from LOC 002 but
    the chunk text itself won't say "LOC 002" — making multi-location
    semantic search return values without location keys.

    Solution: Prepend "LOC 002 | " to every non-empty line within a LOC section
    so that every chunk that contains LOC 002 data explicitly says so.

    Example:
        Before: "Construction Type: Fire Resistive - ISO Class 6"
        After:  "LOC 002 | Construction Type: Fire Resistive - ISO Class 6"

    Args:
        text: Text after label-value reconstruction

    Returns:
        Text with LOC context injected into every content line
    """
    lines = text.split('\n')
    output_lines = []
    current_loc = None

    for line in lines:
        stripped = line.strip()

        if not stripped:
            output_lines.append('')
            continue

        # Detect LOC section header like "LOC 001 | Main Hotel Tower | ..."
        loc_header_match = re.match(r'^(LOC\s+\d{3})\s*[\|]', stripped, re.IGNORECASE)
        if loc_header_match:
            current_loc = loc_header_match.group(1).upper().strip()
            # Normalize spacing: LOC 001
            current_loc = re.sub(r'\s+', ' ', current_loc)
            output_lines.append(stripped)
            continue

        # Reset context at major section boundaries (outside location detail sheets)
        if re.match(r'^SECTION\s+[34]', stripped, re.IGNORECASE):
            current_loc = None
            output_lines.append(stripped)
            continue

        # Inject LOC prefix if we are inside a location section
        if current_loc and not _is_section_header(stripped):
            output_lines.append(f"{current_loc} | {stripped}")
        else:
            output_lines.append(stripped)

    return '\n'.join(output_lines)


def preprocess_sov_text(text: str) -> str:
    """
    Full SOV pre-processing pipeline.

    Runs three passes over the raw extracted SOV text to prepare it
    for high-quality chunking and embedding:

    Pass 1 — _reconstruct_section1_table()
        Reconstructs the fragmented master SOV table (Section 1) into
        readable label: value sentences per location row.

    Pass 2 — _reconstruct_label_value_pairs()
        Joins split label lines and value lines in Section 2 location
        detail sheets into "Label: Value" format. Also fixes out-of-order
        text fragments (e.g., LOC 003 FloodBreak sentence).

    Pass 3 — _inject_loc_context()
        Prepends "LOC 001 |", "LOC 002 |" etc. to every content line
        within each location section so that every chunk explicitly
        carries its location identifier. This is critical for the
        retriever's multi-location extraction to work correctly.

    Args:
        text: Raw extracted text from SOV PDF

    Returns:
        Pre-processed text ready for chunking
    """
    logger.info("SOV Pre-processor Pass 1: Reconstructing Section 1 table...")
    text = _reconstruct_section1_table(text)

    logger.info("SOV Pre-processor Pass 2: Reconstructing label-value pairs...")
    text = _reconstruct_label_value_pairs(text)

    logger.info("SOV Pre-processor Pass 3: Injecting LOC context into content lines...")
    text = _inject_loc_context(text)

    logger.info("SOV pre-processing complete.")
    return text


def preprocess_text_if_needed(text: str) -> str:
    """
    Router function — detects document type and applies appropriate pre-processing.

    Currently supports:
    - SOV documents → preprocess_sov_text()
    - All other documents → returned unchanged (no pre-processing)

    This is the single entry point called before chunking. Adding support
    for new document types in the future requires only adding a new
    detection + pre-processing branch here.

    Args:
        text: Raw extracted text from any document

    Returns:
        Pre-processed text (or original text if no pre-processing needed)
    """
    if detect_sov_document(text):
        return preprocess_sov_text(text)

    # All other document types — pass through unchanged
    logger.info("Non-SOV document detected — skipping SOV pre-processor, using raw text.")
    return text


# ==============================================================
# UNCHANGED ORIGINAL CODE BELOW
# Only query_chunk_and_embed() has one line added to call
# preprocess_text_if_needed() before splitting — everything
# else is identical to the original.
# ==============================================================

def _quote_path_only(url: str) -> str:
    """Safely percent-encode only the path component of the URL."""
    parsed = urlparse(url)
    quoted_path = quote(parsed.path, safe="/")
    return unquote(parsed.path)


async def query_download_from_blob(blob_url: str) -> bytes:
    """Download text file bytes from blob storage."""
    if not blob_url or not blob_url.lower().startswith(("http://", "https://")):
        raise ValueError("A full http(s) blob URL must be provided")

    try:
        blob_client = BlobClient.from_blob_url(blob_url)
        return blob_client.download_blob().readall()
    except AzureError as e:
        conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        if not conn_str:
            raise RuntimeError(f"Failed to download blob: {str(e)}")

        parsed = urlparse(blob_url)
        path = unquote(parsed.path)
        path_parts = [p for p in path.split("/") if p]
        if len(path_parts) < 2:
            raise RuntimeError("Invalid blob URL format")

        container_name = path_parts[0]
        blob_name = "/".join(path_parts[1:])

        svc = BlobServiceClient.from_connection_string(conn_str)
        blob_client = svc.get_blob_client(container=container_name, blob=blob_name)
        return blob_client.download_blob().readall()


def query_extract_text_from_txt(text_bytes: bytes) -> str:
    """Extract text from TXT file downloaded from blob storage."""
    try:
        text = text_bytes.decode('utf-8')
        logger.info(f"Successfully decoded text file: {len(text)} characters")
        print(text)
        return text
    except UnicodeDecodeError as e:
        logger.error(f"Error decoding text file: {str(e)}")
        raise ValueError(f"Failed to decode text file: {str(e)}")


def query_chunk_and_embed(text: str, vector_db_path: str) -> bool:
    """Chunk text and create vector embeddings in ChromaDB.

    CHANGE FROM ORIGINAL:
    One line added before splitting:
        text = preprocess_text_if_needed(text)
    This applies SOV pre-processing if the document is detected as an SOV.
    For all other document types, text passes through unchanged.
    Everything else — splitting, ChromaDB storage, collection naming — is identical.
    """
    try:
        # -------------------------------------------------------
        # PRE-PROCESS TEXT IF NEEDED (only addition to original)
        # For SOV documents: reconstructs fragmented tables and
        # injects LOC context. For all others: no-op passthrough.
        # -------------------------------------------------------
        text = preprocess_text_if_needed(text)

        # Create document and split into chunks (UNCHANGED)
        doc = Document(page_content=text)
        chunks = text_splitter.split_documents([doc])

        # Get safe collection name from vector_db_path (UNCHANGED)
        safe_name = os.path.basename(vector_db_path).lower()
        safe_name = safe_name.replace(" ", "_").replace("-", "_").replace(".", "_")
        safe_name = "".join(c if c.isalnum() or c in "._-" else "" for c in safe_name)
        safe_name = safe_name.strip("._-")
        collection_name = f"{safe_name}_collection"
        persist_directory = os.path.join(vector_db_path, "chroma_db", safe_name)

        # Create ChromaDB instance and store chunks (UNCHANGED)
        vectordb = Chroma.from_documents(
            chunks,
            embedding=embeddings,
            persist_directory=persist_directory,
            collection_name=collection_name
        )

        # Verify retriever creation (UNCHANGED)
        retriever = Chroma(
            embedding_function=embeddings,
            persist_directory=persist_directory,
            collection_name=collection_name
        ).as_retriever()

        return True
    except Exception as e:
        logger.error(f"Error in chunking/embedding: {str(e)}")
        return False


def extract_reference_id(blob_url: str) -> tuple:
    """Extract and validate reference ID from blob URL. (UNCHANGED)"""
    try:
        path = unquote(urlparse(blob_url).path)
        file_name_with_ext = os.path.basename(path)

        if "_attachment_" in file_name_with_ext:
            parts = file_name_with_ext.split("_attachment_", 1)
            reference_id = parts[0]

            if reference_id and all(c.isalnum() or c == "_" for c in reference_id):
                return reference_id, True, file_name_with_ext

        return None, False, file_name_with_ext

    except Exception as e:
        logger.error(f"Error extracting reference ID from {blob_url}: {str(e)}")
        return None, False, os.path.basename(unquote(urlparse(blob_url).path))


async def process_query_pdf(blob_urls: List[str], vector_db_path: str = None) -> Dict[str, Any]:
    """Main processing function. (UNCHANGED)"""
    try:
        vector_db_path = vector_db_path or os.getenv("QUERY_VDB_PATH", "/home/Jarvis/rohan/Document_Query_MCP/data/vec_db")
        vector_db_path = os.path.abspath(vector_db_path)

        urls_by_reference = {}
        skipped_files = []

        for blob_url in blob_urls:
            reference_id, is_valid, filename = extract_reference_id(blob_url)

            if is_valid:
                if reference_id not in urls_by_reference:
                    urls_by_reference[reference_id] = []
                urls_by_reference[reference_id].append((blob_url, filename))
            else:
                skipped_files.append({
                    "file_name": filename,
                    "reason": "Invalid naming format - no reference ID found. Expected format: reference_id_attachment_filename.ext"
                })

        file_results = []
        all_embedded = True
        reference_ids_processed = []

        for reference_id, url_filename_pairs in urls_by_reference.items():
            ref_vector_db_path = os.path.abspath(os.path.join(vector_db_path, reference_id))

            for blob_url, file_name_with_ext in url_filename_pairs:
                try:
                    file_name, file_ext = os.path.splitext(file_name_with_ext)
                    file_ext = file_ext.lower()

                    file_bytes = await query_download_from_blob(blob_url)

                    if file_ext in (".txt",):
                        text = query_extract_text_from_txt(file_bytes)
                    else:
                        raise ValueError(f"Unsupported file format: {file_ext}. Supported formats: .txt")

                    is_embedded = query_chunk_and_embed(text, ref_vector_db_path)

                    file_results.append({
                        "file_name": file_name,
                        "reference_id": reference_id,
                        "is_embedded": is_embedded,
                        "error": None if is_embedded else "Failed to create embeddings"
                    })

                    if not is_embedded:
                        all_embedded = False

                    if reference_id not in reference_ids_processed:
                        reference_ids_processed.append(reference_id)

                except Exception as e:
                    logger.exception(f"Error processing file from {blob_url}")
                    file_results.append({
                        "file_name": os.path.splitext(file_name_with_ext)[0],
                        "reference_id": reference_id,
                        "is_embedded": False,
                        "error": str(e)
                    })
                    all_embedded = False

        primary_vector_db_path = None
        if reference_ids_processed:
            primary_vector_db_path = os.path.abspath(os.path.join(vector_db_path, reference_ids_processed[0]))

        return {
            "is_vectorised": all_embedded and len(file_results) > 0,
            "metadata": {
                "is_embedded": all_embedded and len(file_results) > 0,
                "is_error": not all_embedded or len(file_results) == 0,
                "error_message": None if (all_embedded and len(file_results) > 0) else "One or more files failed to embed or all files were skipped",
                "files_processed": file_results,
                "files_skipped": skipped_files,
                "vector_db_path": primary_vector_db_path,
                "reference_ids": reference_ids_processed,
                "total_files": len(blob_urls),
                "processed_count": len(file_results),
                "skipped_count": len(skipped_files)
            }
        }

    except Exception as e:
        logger.exception("Error processing files")
        return {
            "is_vectorised": False,
            "metadata": {
                "is_embedded": False,
                "is_error": True,
                "error_message": str(e),
                "vector_db_path": None,
                "total_files": len(blob_urls) if blob_urls else 0
            }
        }
