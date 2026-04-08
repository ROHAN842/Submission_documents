-- ============================================================
-- INSERT QUERY — Loss_Run_Document
-- Table: ref_prompt_library
-- Columns: document_type, prompt, extraction_rules
-- ============================================================
-- IMPORTANT: No changes to retriever.py required.
-- This insert query is standalone and works independently
-- of the SOV_Document insert query already in the table.
-- ============================================================

INSERT INTO ref_prompt_library (document_type, prompt, extraction_rules)
VALUES (
  'Loss_Run_Document',

  -- ============================================================
  -- PROMPT
  -- Dynamic and generic for any Loss Run document regardless
  -- of carrier, insured, or number of claims / policy years.
  -- ============================================================
  'You are an expert commercial property insurance underwriter assistant specializing in Loss Run reports.

Your task is to extract structured underwriting data from certified Loss Run documents. These documents typically contain:
- A report identification header section
- A policy year summary table (one row per policy year)
- Individual claim detail blocks (one block per reported claim)
- A no-loss confirmation section
- A loss analytics or summary section
- A carrier certification block

ATTRIBUTE TO EXTRACT: {attribute}

EXTRACTION INSTRUCTION: {instruction}

EXTRACTION RULES:

1. SINGLE-VALUE ATTRIBUTES:
   - If the instruction does not mention multiple claims, multiple policy years, or per-claim extraction, extract a single consolidated value.
   - Return format: {"amount": "VALUE"}

2. MULTI-CLAIM ATTRIBUTES:
   - If the instruction says "for each claim", "per claim", or "across all claims present", this attribute appears once per claim block.
   - Scan ALL claim blocks present in the context (e.g., Claim 1 of 2, Claim 2 of 2, or however they are labeled).
   - Extract the value of this attribute from EACH claim block independently.
   - Return format: {"amount": {"Claim 1": "value1", "Claim 2": "value2"}}
   - Use the claim number or claim identifier as the key exactly as it appears in the document (e.g., "Claim 1", "Claim 2").
   - If a particular claim block does not contain this attribute, use null as its value.

3. MULTI-POLICY-YEAR ATTRIBUTES:
   - If the instruction says "for each policy year", "per policy year", or "across all policy years", this attribute appears once per policy year row in the policy year summary table.
   - Scan ALL policy year rows present in the context.
   - Extract the value of this attribute from EACH policy year row independently.
   - Return format: {"amount": {"2021-22": "value1", "2022-23": "value2", "2023-24": "value3", "2024-25": "value4", "2025-26": "value5"}}
   - Use the policy year label exactly as it appears in the document as the key.
   - If a particular policy year row does not contain this attribute, use null as its value.

4. AGGREGATE / SUMMARY ATTRIBUTES:
   - If the instruction mentions "combined total", "5-year total", "aggregate", "overall", or "across all years", extract the single aggregate or total value stated in the document.
   - Return format: {"amount": "VALUE"}

5. GENERAL RULES:
   - Do NOT guess or infer values not explicitly present in the context.
   - Do NOT fabricate claim numbers, policy years, or identifiers — use only what the document states.
   - Preserve original formatting of values (e.g., "$41,800.00", "CLOSED – Q3 2022", "April 1, 2021").
   - If the attribute is genuinely not found anywhere in the context, return {"amount": null}.
   - Do NOT add explanations, commentary, or markdown — return ONLY the JSON object.

RESPONSE FORMAT EXAMPLES:
   Single value       → {"amount": "Azul Biscayne Resort & Spa, LLC"}
   Multi-claim        → {"amount": {"Claim 1": "Water Damage", "Claim 2": "Wind-Driven Rain"}}
   Multi-policy-year  → {"amount": {"2021-22": "$0.00", "2022-23": "$41,800.00", "2023-24": "$30,600.00", "2024-25": "$0.00", "2025-26": "$0.00"}}
   Not found          → {"amount": null}

CONTEXT (extracted chunks from the Loss Run document):
{context}',

  -- ============================================================
  -- EXTRACTION RULES (JSONB)
  -- 51 attributes — all unique, covering report identification,
  -- policy year summary, per-claim details, no-loss confirmations,
  -- loss analytics, and carrier certification.
  -- ============================================================
  '{
    "Named Insured": {
      "description": "Legal name of the insured entity as stated in the report identification section of the loss run."
    },
    "DBA / Trade Name": {
      "description": "Doing-business-as or trade name of the insured entity if different from the legal name, as stated in the report identification section."
    },
    "Insured Address": {
      "description": "Full mailing or property address of the insured as stated in the report identification section of the loss run."
    },
    "Issuing Carrier": {
      "description": "Name of the insurance carrier or company that issued the policy and prepared this loss run report."
    },
    "Policy Number": {
      "description": "Primary or most recent policy number as stated in the report identification section of the loss run."
    },
    "Policy Period Covered": {
      "description": "Overall date range covered by this loss run report (start date to end date) as stated in the report identification section."
    },
    "Loss Run Period": {
      "description": "Specific period for which loss data is reported in this loss run, as stated in the report identification section."
    },
    "Report Prepared By": {
      "description": "Name of the department or entity that prepared this loss run report, as stated in the report identification section."
    },
    "Report Date": {
      "description": "Date on which this loss run report was prepared, as stated in the report identification section."
    },
    "Requesting Broker": {
      "description": "Name of the brokerage firm that requested this loss run report, as stated in the report identification section."
    },
    "Broker Contact": {
      "description": "Name, phone number, and email address of the broker contact who requested this loss run, as stated in the report identification section."
    },
    "Certification Status": {
      "description": "Certification type and purpose of this loss run report (e.g., Certified Loss Run, prepared for submission purposes), as stated in the report identification section."
    },
    "Policy Year List": {
      "description": "All policy years covered in this loss run report as listed in the policy year summary table, for each policy year present in the document. Return the value for each policy year independently, keyed by policy year label."
    },
    "Policy Number Per Year": {
      "description": "Policy number assigned for each policy year as listed in the policy year summary table, for each policy year present in the document. Return the value for each policy year independently, keyed by policy year label."
    },
    "Effective Date Per Year": {
      "description": "Policy effective date for each policy year as listed in the policy year summary table, for each policy year present in the document. Return the value for each policy year independently, keyed by policy year label."
    },
    "Expiration Date Per Year": {
      "description": "Policy expiration date for each policy year as listed in the policy year summary table, for each policy year present in the document. Return the value for each policy year independently, keyed by policy year label."
    },
    "Losses Reported Per Year": {
      "description": "Number of losses or claims reported for each policy year as listed in the policy year summary table, for each policy year present in the document. Return the value for each policy year independently, keyed by policy year label."
    },
    "Total Incurred Per Year": {
      "description": "Total incurred loss amount for each policy year as listed in the policy year summary table, for each policy year present in the document. Return the value for each policy year independently, keyed by policy year label."
    },
    "Policy Year Status": {
      "description": "Status of each policy year (e.g., Closed, Open / Current) as listed in the policy year summary table, for each policy year present in the document. Return the value for each policy year independently, keyed by policy year label."
    },
    "5-Year Total Claims Count": {
      "description": "Total number of claims reported across all policy years combined, as stated in the policy year summary totals row or loss analytics section."
    },
    "5-Year Total Incurred": {
      "description": "Total combined incurred loss amount across all policy years as stated in the policy year summary totals row or loss analytics section."
    },
    "Total Reported Claims": {
      "description": "Total number of claims reported across the entire loss run period as stated in the detailed claim register section header or loss analytics section."
    },
    "Open Claims Count": {
      "description": "Number of currently open or pending claims as stated in the loss analytics section or claim register."
    },
    "Claim Number": {
      "description": "Unique claim number or identifier assigned by the carrier for each claim, for each claim present in the document. Return the value for each claim independently, keyed by claim number (e.g., Claim 1, Claim 2)."
    },
    "Claim Policy Year": {
      "description": "Policy year to which each claim belongs as stated in the claim detail block header, for each claim present in the document. Return the value for each claim independently, keyed by claim number."
    },
    "Claim Type / Peril": {
      "description": "Type of loss or peril category for each claim as stated in the claim detail block header (e.g., Water Damage, Wind-Driven Rain, Fire), for each claim present in the document. Return the value for each claim independently, keyed by claim number."
    },
    "Claim Location": {
      "description": "Building or area within the property where each claim occurred as stated in the claim detail block, for each claim present in the document. Return the value for each claim independently, keyed by claim number."
    },
    "Claim Address": {
      "description": "Full street address of the location where each claim occurred as stated in the claim detail block, for each claim present in the document. Return the value for each claim independently, keyed by claim number."
    },
    "Date of Loss": {
      "description": "Date on which each insured loss event occurred as stated in the claim detail block, for each claim present in the document. Return the value for each claim independently, keyed by claim number."
    },
    "Date Reported": {
      "description": "Date on which each claim was reported to the carrier as stated in the claim detail block, for each claim present in the document. Return the value for each claim independently, keyed by claim number."
    },
    "Line of Business": {
      "description": "Line of business under which each claim was filed (e.g., Commercial Property – Building and Contents) as stated in the claim detail block, for each claim present in the document. Return the value for each claim independently, keyed by claim number."
    },
    "Cause of Loss": {
      "description": "Specific cause or mechanism of loss for each claim as stated in the claim detail block (e.g., domestic supply line failure, roof flashing failure), for each claim present in the document. Return the value for each claim independently, keyed by claim number."
    },
    "Loss Description": {
      "description": "Narrative description of what occurred, the damage sustained, and the remediation actions taken for each claim as stated in the claim detail block, for each claim present in the document. Return the value for each claim independently, keyed by claim number."
    },
    "Gross Incurred": {
      "description": "Total gross amount incurred before deductible for each claim as stated in the claim detail block, for each claim present in the document. Return the value for each claim independently, keyed by claim number."
    },
    "Deductible Applied": {
      "description": "Deductible amount applied to each claim as stated in the claim detail block, for each claim present in the document. Return the value for each claim independently, keyed by claim number."
    },
    "Net Paid (Carrier)": {
      "description": "Net amount paid by the carrier after deductible for each claim as stated in the claim detail block, for each claim present in the document. Return the value for each claim independently, keyed by claim number."
    },
    "Reserve / Outstanding": {
      "description": "Outstanding reserve amount remaining for each claim as stated in the claim detail block, for each claim present in the document. Return the value for each claim independently, keyed by claim number."
    },
    "Total Incurred Net Per Claim": {
      "description": "Total net incurred amount for each individual claim as stated in the claim detail block, for each claim present in the document. Return the value for each claim independently, keyed by claim number."
    },
    "Claim Status": {
      "description": "Current status and closure details for each claim (e.g., Closed – Q3 2022, Open) as stated in the claim detail block, for each claim present in the document. Return the value for each claim independently, keyed by claim number."
    },
    "Adjuster / TPA": {
      "description": "Name of the adjuster or third-party administrator handling each claim and their reference number, as stated in the claim detail block, for each claim present in the document. Return the value for each claim independently, keyed by claim number."
    },
    "Litigation Status": {
      "description": "Litigation or legal dispute status for each claim as stated in the claim detail block (e.g., None, In Litigation), for each claim present in the document. Return the value for each claim independently, keyed by claim number."
    },
    "BI Invoked": {
      "description": "Whether business interruption coverage was triggered or invoked for each claim as stated in the claim detail block (e.g., Yes or No), for each claim present in the document. Return the value for each claim independently, keyed by claim number."
    },
    "No-Loss Policy Years": {
      "description": "List of policy years confirmed as having no losses reported or incurred, along with the confirmation statement and certifying party, as stated in the no-loss confirmation section of the loss run."
    },
    "5-Year Claim Count (Analytics)": {
      "description": "Total claim count as reported in the loss analytics summary section, along with any benchmark or industry comparison comment stated in the document."
    },
    "5-Year Total Incurred (Analytics)": {
      "description": "Total incurred loss amount as reported in the loss analytics summary section, along with any benchmark or underwriting disposition comment stated in the document."
    },
    "Average Loss Per Claim": {
      "description": "Average loss amount per claim as stated in the loss analytics summary section, along with any benchmark comment."
    },
    "Largest Single Loss": {
      "description": "Largest individual claim amount and its details (date, cause) as stated in the loss analytics summary section."
    },
    "5-Year Loss Ratio": {
      "description": "Estimated 5-year loss ratio percentage as stated in the loss analytics summary section, including the premium basis used for calculation if stated."
    },
    "Prior Carrier Departure Reason": {
      "description": "Reason for prior carrier non-renewal or departure as stated in the loss analytics summary section, including any underwriting disposition note."
    },
    "Certification Signatory": {
      "description": "Name, title, and department of the authorized individual or entity who signed and certified this loss run report, as stated in the carrier certification section."
    },
    "Certification Date": {
      "description": "Date on which this loss run report was certified and signed, as stated in the carrier certification section."
    }
  }'::jsonb
);
