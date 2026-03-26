-- ============================================================
-- INSERT QUERY — SOV_Document
-- Table: ref_prompt_library
-- Columns: document_type, prompt, extraction_rules
-- ============================================================

INSERT INTO ref_prompt_library (document_type, prompt, extraction_rules)
VALUES (
  'SOV_Document',

  -- ============================================================
  -- PROMPT
  -- ============================================================
  'You are an expert commercial property insurance underwriter assistant specializing in Statement of Values (SOV) documents.

Your task is to extract structured underwriting data from SOV documents which may contain multiple insured locations organized into numbered sections (e.g., LOC 001, LOC 002, Location 1, Site A, etc.).

ATTRIBUTE TO EXTRACT: {attribute}

EXTRACTION INSTRUCTION: {instruction}

EXTRACTION RULES:

1. SINGLE-VALUE ATTRIBUTES:
   - If the instruction does not mention multiple locations or sections, extract a single consolidated value.
   - Return format: {"amount": "VALUE"}

2. MULTI-LOCATION / MULTI-SECTION ATTRIBUTES:
   - If the instruction says "for each insured location", "across all locations", or "capturing all locations present", this attribute appears in multiple location sections.
   - Scan ALL location sections present in the context (e.g., LOC 001, LOC 002, LOC 003, LOC 004, or however they are labeled).
   - Extract the value of this attribute from EACH location section independently.
   - Return format: {"amount": {"LOC 001": "value1", "LOC 002": "value2", "LOC 003": "value3", "LOC 004": "value4"}}
   - Use whatever location identifier label is present in the document as the key (e.g., "LOC 001", "Location 1", "Site A").
   - If a particular location section does not contain this attribute, use null as its value.

3. AGGREGATE / TOTAL ATTRIBUTES:
   - If the instruction mentions "combined", "sum", "across all locations", or "grand total", extract the single aggregate or total value stated in the document.
   - Return format: {"amount": "VALUE"}

4. GENERAL RULES:
   - Do NOT guess or infer values not explicitly present in the context.
   - Do NOT fabricate location identifiers — use only what the document states.
   - Preserve original formatting of values (e.g., "$128,500,000", "Fire Resistive — ISO Class 6", "April 1, 2026").
   - If the attribute is genuinely not found anywhere in the context, return {"amount": null}.
   - Do NOT add explanations, commentary, or markdown — return ONLY the JSON object.

RESPONSE FORMAT EXAMPLES:
   Single value   → {"amount": "2900 Biscayne Boulevard, Miami, FL 33137"}
   Multi-location → {"amount": {"LOC 001": "Fire Resistive Class 6", "LOC 002": "Fire Resistive Class 6", "LOC 003": "Non-Combustible Light Steel", "LOC 004": "Non-Combustible Light Steel"}}
   Not found      → {"amount": null}

CONTEXT (extracted chunks from the SOV document):
{context}',

  -- ============================================================
  -- EXTRACTION RULES (JSONB)
  -- 56 attributes — all unique, no duplication across locations
  -- ============================================================
  '{
    "Named Insured": {
      "description": "Legal name of the insured entity as stated on the SOV, typically found in the SOV identification section at the top of the document."
    },
    "DBA / Trade Name": {
      "description": "Doing-business-as or trade name of the insured entity if different from the legal name, as stated in the SOV identification section."
    },
    "Property Address": {
      "description": "Primary property address of the insured as listed in the SOV identification section at the top of the document."
    },
    "Policy Period": {
      "description": "Start and end dates of the insurance coverage period as stated in the SOV identification section."
    },
    "SOV Date": {
      "description": "Date on which this Statement of Values was prepared, as stated in the SOV identification section."
    },
    "SOV Prepared By": {
      "description": "Name of the entity or firm responsible for preparing this Statement of Values, as stated in the SOV identification section."
    },
    "Valuation Basis": {
      "description": "Method used to value the insured properties (e.g., Full Replacement Cost Value, Actual Cash Value), including the name of the valuation standard or tool referenced."
    },
    "Appraisal Provider": {
      "description": "Name of the independent appraisal firm and the appraiser who conducted the property valuation, including their credentials if stated."
    },
    "Appraisal Date": {
      "description": "Date on which the property appraisal was conducted, as referenced in the SOV."
    },
    "Insurance-to-Value Status": {
      "description": "Confirmation of the overall insurance-to-value percentage and coinsurance basis across all locations (e.g., 100% ITV confirmed, Agreed Value basis, no coinsurance deficiency)."
    },
    "Inflation Guard": {
      "description": "Annual indexing percentage applied to property values as recommended by the appraiser and stated in the SOV identification section."
    },
    "Mortgage / Lienholder": {
      "description": "Name of the mortgagee or lienholder, lien type, and any financial metrics (e.g., DSCR) associated with the mortgage, as stated in the SOV."
    },
    "Requesting Broker": {
      "description": "Full name of the brokerage firm and the individual broker contact who submitted this SOV, including their professional designations if stated."
    },
    "Broker License": {
      "description": "Professional license number of the submitting broker as stated in the SOV certification or attestation section."
    },
    "Broker Address": {
      "description": "Office address of the submitting brokerage firm as stated in the SOV certification or attestation section."
    },
    "Certification Signatory": {
      "description": "Full name, professional designation, and job title of the authorized individual who signed and certified the SOV on behalf of the broker."
    },
    "Location Number": {
      "description": "Identifier assigned to each insured location as listed in the SOV (e.g., 001, 002, 003, 004). For each insured location capturing all locations present, return all location identifiers present in the document."
    },
    "Location Description / Occupancy": {
      "description": "Description and occupancy type for each insured location as listed in the SOV, capturing all locations present. Return the value for each location section independently, keyed by location identifier."
    },
    "Full Address": {
      "description": "Full street address including city, state, and zip code for each insured location as listed in the SOV location detail sections, capturing all locations present. Return the value for each location section independently, keyed by location identifier."
    },
    "Occupancy Type": {
      "description": "Formal occupancy classification including ISO code and NAICS code where available for each insured location, capturing all locations present. Return the value for each location section independently, keyed by location identifier."
    },
    "Construction Type": {
      "description": "Construction classification and ISO class for each insured location (e.g., Fire Resistive Class 6, Non-Combustible Light Steel Frame), capturing all locations present. Return the value for each location section independently, keyed by location identifier."
    },
    "Year Built / Renovated": {
      "description": "Year of original construction and year of last major renovation along with renovation cost and scope summary for each insured location, capturing all locations present. Return the value for each location section independently, keyed by location identifier."
    },
    "Gross Building Area (Sq Ft)": {
      "description": "Total gross square footage for each insured location as stated in the SOV location detail sections, capturing all locations present. Return the value for each location section independently, keyed by location identifier."
    },
    "Number of Stories / Levels": {
      "description": "Total number of floors or levels for each insured location as stated in the SOV, capturing all locations present. Return the value for each location section independently, keyed by location identifier."
    },
    "Roof Type & Age": {
      "description": "Roof system type, material, and replacement or installation year for each insured location as stated in the SOV, capturing all locations present. Return the value for each location section independently, keyed by location identifier."
    },
    "Sprinkler System": {
      "description": "Fire sprinkler system type (e.g., NFPA 13 Wet Pipe), coverage percentage, last inspection date, and any deficiency notes for each insured location, capturing all locations present. Return the value for each location section independently, keyed by location identifier."
    },
    "Fire Alarm": {
      "description": "Fire alarm system description, monitoring type, vendor, and last test date for each insured location, capturing all locations present. Return the value for each location section independently, keyed by location identifier."
    },
    "Fire Protection (Non-Sprinkler)": {
      "description": "Fire protection systems used where full sprinkler coverage is not applicable, such as dry standpipe systems, portable extinguishers, or open-air design rationale, for each insured location, capturing all locations present. Return the value for each location section independently, keyed by location identifier."
    },
    "FEMA Flood Zone": {
      "description": "FEMA flood zone designation, base flood elevation, first floor elevation, and any flood mitigation measures for each insured location, capturing all locations present. Return the value for each location section independently, keyed by location identifier."
    },
    "Flood Mitigation Details": {
      "description": "Specific flood barrier systems installed, their inundation ratings, and below-grade MEP protection details for each insured location where flood mitigation is referenced, capturing all locations present. Return the value for each location section independently, keyed by location identifier."
    },
    "Wind Zone": {
      "description": "Wind zone classification, design wind speed, and glazing or structural wind resistance details for each insured location, capturing all locations present. Return the value for each location section independently, keyed by location identifier."
    },
    "Building RCV": {
      "description": "Building replacement cost value and the per-square-foot rate for each insured location as per the appraisal, capturing all locations present. Return the value for each location section independently, keyed by location identifier."
    },
    "BPP / Contents Value": {
      "description": "Business personal property and contents value including itemized categories (e.g., FF&E, equipment, fixtures) for each insured location, capturing all locations present. Return the value for each location section independently, keyed by location identifier."
    },
    "Business Income / Extra Expense": {
      "description": "Business income and extra expense allocation amount and percentage for each insured location, capturing all locations present. Return the value for each location section independently, keyed by location identifier."
    },
    "Total Insured Value (TIV)": {
      "description": "Total insured value combining Building RCV, BPP, and BI allocation for each insured location as stated in the SOV, capturing all locations present. Return the value for each location section independently, keyed by location identifier."
    },
    "ITV Status": {
      "description": "Insurance-to-value certification status and valuation confirmation for each insured location as stated in the ITV certification section, capturing all locations present. Return the value for each location section independently, keyed by location identifier."
    },
    "Prior Loss Note": {
      "description": "Any prior loss history, claim amount, date, cause, and remediation status noted for each insured location, capturing all locations present. Return the value for each location section independently, keyed by location identifier."
    },
    "Renovation Scope": {
      "description": "Description of renovation work completed including scope, total cost, and year for each insured location where a renovation is referenced, capturing all locations present. Return the value for each location section independently, keyed by location identifier."
    },
    "Parking Capacity": {
      "description": "Total number of parking spaces, number of levels, and operational details such as valet or self-park for the parking structure location if present in the SOV."
    },
    "Total Gross Building Area": {
      "description": "Combined total square footage across all insured locations as stated in the master SOV summary or totals row."
    },
    "Total Building RCV": {
      "description": "Sum of building replacement cost values across all insured locations as stated in the master SOV summary or totals row."
    },
    "Total BPP / Contents": {
      "description": "Sum of all business personal property and contents values across all insured locations as stated in the master SOV summary or totals row."
    },
    "Total BI / Extra Expense Limit": {
      "description": "Combined business income and extra expense limit across all locations as stated in the SOV business income note or summary section."
    },
    "Grand Total TIV": {
      "description": "Grand total insured value including building RCV, BPP, and BI across all insured locations as stated in the SOV totals section."
    },
    "BI Indemnity Period": {
      "description": "Selected business income indemnity period in months and the rationale provided for that selection, as stated in the SOV business income section."
    },
    "BI Extra Expense Sublimit": {
      "description": "Extra expense sublimit amount within the combined business income and extra expense coverage, as stated in the SOV."
    },
    "Annual Gross Revenue": {
      "description": "Gross revenue figures by year as provided in the SOV business income section to support the BI limit selection (e.g., 2023, 2024, 2025 figures)."
    },
    "Average Daily Rate (ADR)": {
      "description": "Average daily room rate as stated in the SOV business income or occupancy section."
    },
    "Occupancy Rate": {
      "description": "Property occupancy rate percentage and room night statistics as stated in the SOV business income or location detail section."
    },
    "Number of Guest Rooms": {
      "description": "Total number of guest rooms and suites in the main hotel tower as stated in the SOV location detail section."
    },
    "F&B Outlets": {
      "description": "Names and descriptions of food and beverage outlets within the hotel property as stated in the SOV."
    },
    "Spa & Fitness Area": {
      "description": "Size in square feet and description of spa and fitness center facilities as stated in the SOV location detail section."
    },
    "Backup Power": {
      "description": "Generator capacity in kilowatts, fuel supply duration, transfer switch type, and testing frequency for the main tower as stated in the SOV."
    },
    "Security System": {
      "description": "CCTV camera count and storage details, security personnel staffing, and access control system description for the main tower as stated in the SOV."
    },
    "Seismic Zone": {
      "description": "Seismic hazard zone classification and probable maximum loss percentage for the property as stated in the SOV."
    },
    "Building Code Compliance": {
      "description": "Building code edition, compliance status, and permit closure status following the most recent renovation as stated in the SOV."
    }
  }'::jsonb
);
