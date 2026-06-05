"""
Comprehensive list of core keys found in Hotel Management Agreement (HMA) files
Extracted from pymupdf_markdowns folder
Total: 127 unique keys
"""

CORE_KEYS = [
    # ===========================
    # I. GENERAL / IDENTITY
    # ===========================
    "Name of Hotel",
    "Hotel Opening Date",
    "Hotel/Lodge Opening Date",
    "No. of Rooms",
    "Region",
    "Site Details",
    "Nature of Right of Owner",
    "Nature of Right of Lessee",
    "Nature of Right of Lessor",
    "Nature of Right of Licensee",
    "Nature of Right of Licensor",
    "Nature of Right of IHCL",
    "Nature of Right of JMHL",
    "Additional Construction, if any",
    "Mortgage Limit",

    # ===========================
    # II. PARTIES
    # ===========================
    "Owner Details and Address",
    "Owner/Promoter Details and Address",
    "Operator details and Address",
    "First Party Details and address",
    "Second Party Details and address",
    "Lessor Details and address",
    "Lessee Details and address",
    "Licensor Details and address",
    "Licensee Details and address",

    # ===========================
    # III. TERM & VALIDITY
    # ===========================
    "Original Execution Date",
    "Original Term",
    "Valid from",
    "Valid From",
    "Valid up to",
    "Lock-in Period, if any",
    "Lock-in period, if any",
    "Original Documents Location (place)",
    "Original Documents location (place)",

    # ===========================
    # IV. RENEWAL
    # ===========================
    "Renewal Term",
    "Conditions of Renewal",
    "Renewal Notice Period",
    "Renewal Notice period",
    "Non-Renewal Notice Period",

    # ===========================
    # V. SUPPLEMENTAL AGREEMENTS
    # ===========================
    "Execution Date",
    "Any other amendments in the Supplemental Agreement",
    "Any amendment in Supplemental Agreement",
    "Any other amendments in the Novation Agreement",

    # ===========================
    # VI. OPERATIONS
    # ===========================
    "Key Personnel",
    "Key Personnel / Appointment",

    # ===========================
    # VII. ANNUAL PLAN & BUDGET
    # ===========================
    "Approval of Owner",
    "Approval of Owner/Promoter",
    "Owner's Approval",
    "Operating Budget",
    "Operational Plan",
    "Annual Plan",
    "Reserve Fund Work Budget",
    "Capital Expenditure",
    "FF&FE Contribution",
    "FF&E Contribution",
    "Notional FF&FE",
    "Working Capital Clause",

    # ===========================
    # VIII. COMPENSATION / FEES
    # ===========================
    "Management Fee",
    "Incentive Fee",
    "Sales & Marketing Fee",
    "Sales and Marketing Fee",
    "Sales & Marketing Fee & Central Group Services Fee",
    "Central Group Services Fee",
    "Central Group SErvices Fee",
    "Loyalty Program Fee",
    "Technical Service Fees",
    "Technical fees",
    "TSA",
    "Reservation FEe",
    "IT Systems fee",
    "Reimbursables",
    "Earnest Money Deposit / Key Money",
    "Earnest Money Deposit",
    "Refundable Deposit",
    "Non Refundable Deposit",
    "Premium paid",
    "Performance Security",
    "Consideration",
    "Applicable Fee / Rent Fee / Consideration Payable",
    "Minimum Guarantee",
    "CAP to Fees",
    "Cap",

    # ===========================
    # IX. FINANCIAL TERMS
    # ===========================
    "Owner's Priority",
    "Owner's Privilege",
    "Promoter's Priority",
    "Owner's Corporate Office Expenses",
    "Due date of Payment",
    "Interest on delayed Payment",
    "Reconciliation Schedule",

    # ===========================
    # X. BANK ACCOUNTS
    # ===========================
    "Bank Accounts",

    # ===========================
    # XI. PERFORMANCE
    # ===========================
    "Performance Testing Terms",

    # ===========================
    # XII. TERMINATION
    # ===========================
    "Cure Period",
    "Cure Right",
    "Termination at Will",
    "Termination at will",
    "Termination at Will by Owner",
    "Termination at will IHCL",
    "Termination by Owner",
    "Termination by Operator",
    "Termination By IHCL",
    "Termination By Lessor",
    "Termination By Lessee",
    "Termination By Licensee",
    "Termination By JMHL",
    "Liquidated Damages",
    "Consequences of Termination",
    "Premature Termination Compensation",
    "Right to building upon termination",
    "Right to building upon termination by JMHL",
    "Right to building upon termination by Lessor",
    "Rights of removal of Assets on Termination",
    "Ownership of Assets",

    # ===========================
    # XIII. RESTRICTIONS & COMPLIANCE
    # ===========================
    "Non-compete Clause",
    "Non-compete Clause Area of Protection",
    "Area of Protection",
    "Sale Transfer Clause",
    "Sale Transfer Clause and Assignment",
    "Sale Transfer Clause Assignment",
    "Assignment",
    "Right of sale/transfer",
    "Right to create encumbrance",
    "Permission / Approval needed for which acts",
    "Procedure for Approval",

    # ===========================
    # XIV. LEGAL
    # ===========================
    "Governing Law and Jurisdiction",
    "Jurisdiction",
    "Arbitration",
    "Signatory",

    # ===========================
    # XV. MISCELLANEOUS
    # ===========================
    "Others",
]


# Categorized version for easier navigation and programmatic access
CORE_KEYS_CATEGORIZED = {
    "Identity": [
        "Name of Hotel",
        "Hotel Opening Date",
        "Hotel/Lodge Opening Date",
        "No. of Rooms",
        "Region",
        "Site Details",
        "Nature of Right of Owner",
        "Nature of Right of Lessee",
        "Nature of Right of Lessor",
        "Nature of Right of Licensee",
        "Nature of Right of Licensor",
        "Nature of Right of IHCL",
        "Nature of Right of JMHL",
        "Additional Construction, if any",
        "Mortgage Limit",
    ],

    "Parties": [
        "Owner Details and Address",
        "Owner/Promoter Details and Address",
        "Operator details and Address",
        "First Party Details and address",
        "Second Party Details and address",
        "Lessor Details and address",
        "Lessee Details and address",
        "Licensor Details and address",
        "Licensee Details and address",
    ],

    "Term": [
        "Original Execution Date",
        "Original Term",
        "Valid from",
        "Valid From",
        "Valid up to",
        "Lock-in Period, if any",
        "Lock-in period, if any",
        "Original Documents Location (place)",
        "Original Documents location (place)",
    ],

    "Renewal": [
        "Renewal Term",
        "Conditions of Renewal",
        "Renewal Notice Period",
        "Renewal Notice period",
        "Non-Renewal Notice Period",
    ],

    "Supplemental": [
        "Execution Date",
        "Any other amendments in the Supplemental Agreement",
        "Any amendment in Supplemental Agreement",
        "Any other amendments in the Novation Agreement",
    ],

    "Operations": [
        "Key Personnel",
        "Key Personnel / Appointment",
    ],

    "Budget_Planning": [
        "Approval of Owner",
        "Approval of Owner/Promoter",
        "Owner's Approval",
        "Operating Budget",
        "Operational Plan",
        "Annual Plan",
        "Reserve Fund Work Budget",
        "Capital Expenditure",
        "FF&FE Contribution",
        "FF&E Contribution",
        "Notional FF&FE",
        "Working Capital Clause",
    ],

    "Fees_Compensation": [
        "Management Fee",
        "Incentive Fee",
        "Sales & Marketing Fee",
        "Sales and Marketing Fee",
        "Sales & Marketing Fee & Central Group Services Fee",
        "Central Group Services Fee",
        "Central Group SErvices Fee",
        "Loyalty Program Fee",
        "Technical Service Fees",
        "Technical fees",
        "TSA",
        "Reservation FEe",
        "IT Systems fee",
        "Reimbursables",
        "Earnest Money Deposit / Key Money",
        "Earnest Money Deposit",
        "Refundable Deposit",
        "Non Refundable Deposit",
        "Premium paid",
        "Performance Security",
        "Consideration",
        "Applicable Fee / Rent Fee / Consideration Payable",
        "Minimum Guarantee",
        "CAP to Fees",
        "Cap",
    ],

    "Financial_Terms": [
        "Owner's Priority",
        "Owner's Privilege",
        "Promoter's Priority",
        "Owner's Corporate Office Expenses",
        "Due date of Payment",
        "Interest on delayed Payment",
        "Reconciliation Schedule",
        "Bank Accounts",
    ],

    "Performance": [
        "Performance Testing Terms",
    ],

    "Termination": [
        "Cure Period",
        "Cure Right",
        "Termination at Will",
        "Termination at will",
        "Termination at Will by Owner",
        "Termination at will IHCL",
        "Termination by Owner",
        "Termination by Operator",
        "Termination By IHCL",
        "Termination By Lessor",
        "Termination By Lessee",
        "Termination By Licensee",
        "Termination By JMHL",
        "Liquidated Damages",
        "Consequences of Termination",
        "Premature Termination Compensation",
        "Right to building upon termination",
        "Right to building upon termination by JMHL",
        "Right to building upon termination by Lessor",
        "Rights of removal of Assets on Termination",
        "Ownership of Assets",
    ],

    "Restrictions": [
        "Non-compete Clause",
        "Non-compete Clause Area of Protection",
        "Area of Protection",
        "Sale Transfer Clause",
        "Sale Transfer Clause and Assignment",
        "Sale Transfer Clause Assignment",
        "Assignment",
        "Right of sale/transfer",
        "Right to create encumbrance",
        "Permission / Approval needed for which acts",
        "Procedure for Approval",
    ],

    "Legal": [
        "Governing Law and Jurisdiction",
        "Jurisdiction",
        "Arbitration",
        "Signatory",
    ],

    "Miscellaneous": [
        "Others",
    ],
}


# High-priority keys for embedding/querying (commonly queried fields)
HIGH_PRIORITY_KEYS = [
    # Identity
    "Name of Hotel",
    "Hotel Opening Date",
    "No. of Rooms",

    # Fee-related (ALL of them)
    "Management Fee",
    "Incentive Fee",
    "Sales & Marketing Fee",
    "Sales & Marketing Fee & Central Group Services Fee",
    "Central Group Services Fee",
    "Loyalty Program Fee",
    "Reimbursables",
    "Earnest Money Deposit / Key Money",

    # Term
    "Original Execution Date",
    "Original Term",
    "Valid from",
    "Valid up to",

    # Renewal
    "Renewal Term",
    "Renewal Notice Period",

    # Budget
    "FF&FE Contribution",
    "Working Capital Clause",

    # Termination
    "Termination by Owner",
    "Termination by Operator",
    "Liquidated Damages",

    # Legal
    "Governing Law and Jurisdiction",
]


if __name__ == "__main__":
    print(f"Total unique core keys found: {len(CORE_KEYS)}")
    print(f"\nKeys by category:")
    for category, keys in CORE_KEYS_CATEGORIZED.items():
        print(f"  {category}: {len(keys)} keys")
    print(f"\nHigh priority keys: {len(HIGH_PRIORITY_KEYS)}")
