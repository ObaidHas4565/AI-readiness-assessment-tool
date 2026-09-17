# Data Dictionary

Column reference for the AI Adoption Readiness assessment dataset.

## Context columns

| Column | Meaning | Allowed values |
|---|---|---|
| `company_id` | Synthetic row identifier | SYN0001, SYN0002, ... |
| `profile` | Readiness profile used (synthetic data only; absent from real data) | `Early_Stage_Adopter`, `Well_Funded`, `Tech_Focused`, `Traditional_Company`, `Developing`, `Leadership_Driven`, `Governance_Focused`, `Advanced_Adopter` |
| `industry_sector` | Industry sector | `Retail`, `Technology`, `Manufacturing`, `Marketing`, `Healthcare`, `Other` |
| `employee_band` | Number of employees | `1-9`, `10-49`, `50-249`, `250+` |
| `years_in_operation` | Years in operation | `Under 2 years`, `2-5 years`, `6-10 years`, `10+ years` |
| `region` | Region / country of operation | `UAE`, `UK`, `India`, `USA`, `Other` |
| `current_ai_stage` | Current stage of AI adoption | `Not considering`, `Exploring`, `Piloting`, `Actively Using`, `Fully Integrated` |

None of these context columns is scored. They provide segmentation context only. `current_ai_stage` is ordinal and is the outcome variable against which empirical factor weights would be derived.

## Response scale

Every readiness column holds a **raw** answer on a 5-point agreement scale:

| Value | Label |
|---|---|
| 5 | Strongly Agree |
| 4 | Agree |
| 3 | Neutral |
| 2 | Disagree |
| 1 | Strongly Disagree |

**Reverse-worded items are marked below.** For these, the statement describes a *barrier*, so agreeing indicates LOWER readiness. The scoring engine re-codes them as `6 - raw` before averaging. Values in the CSV are raw, exactly as a respondent would answer.

## Readiness columns

### Budget & Financial Readiness

Weight: `0.1429` &nbsp;|&nbsp; Items: 4

| Column | Statement | Reverse? |
|---|---|---|
| `BUD_1` | We have a dedicated budget for AI adoption or experimentation. | No |
| `BUD_2` | Financial cost is the current barrier in AI adoption. | **Yes** |
| `BUD_3` | We can access external funding or grants for technology adoption if needed. | No |
| `BUD_4` | Leadership would approve for investment in AI adoption if return on investment is clearly shown. | No |

### Workforce & Skill Readiness

Weight: `0.1429` &nbsp;|&nbsp; Items: 4

| Column | Statement | Reverse? |
|---|---|---|
| `WRK_1` | Staff having the required technical skills needed to use AI tools effectively. | No |
| `WRK_2` | We provide training opportunities to employees for AI-related skills. | No |
| `WRK_3` | We have identified specific skill gaps that block AI adoption. | **Yes** |
| `WRK_4` | Staff are generally open to use AI tools in their work. | No |

### Leadership & Strategic Readiness

Weight: `0.1429` &nbsp;|&nbsp; Items: 5

| Column | Statement | Reverse? |
|---|---|---|
| `LDR_1` | Leadership views AI adoption as low priority right now. | **Yes** |
| `LDR_2` | Leadership actively supports AI adoption initiatives. | No |
| `LDR_3` | We have clear strategic vision for how AI fits into our business goals. | No |
| `LDR_4` | Leadership regularly communicates the reasons and benefits of AI adoption to staff. | No |
| `LDR_5` | Decision-makers understand the basic capabilities and limitations of AI tools. | No |

### Data Readiness

Weight: `0.1429` &nbsp;|&nbsp; Items: 5

| Column | Statement | Reverse? |
|---|---|---|
| `DAT_1` | Our company data is well-organized and easily accessible. | No |
| `DAT_2` | We trust the quality and accuracy of our existing data. | No |
| `DAT_3` | We have processes in place for managing and governing data. | No |
| `DAT_4` | We could provide the data an AI tool would need if we adopted one. | No |
| `DAT_5` | Poor data quality is the current barrier to using AI tools in our company. | **Yes** |

### Technology & IT Infrastructure Readiness

Weight: `0.1429` &nbsp;|&nbsp; Items: 5

| Column | Statement | Reverse? |
|---|---|---|
| `TEC_1` | Current IT infrastructure could support new AI tools. | No |
| `TEC_2` | Integrated systems that could connect with AI systems. | No |
| `TEC_3` | We have IT support capable for maintaining AI tools. | No |
| `TEC_4` | We have previously adopted new digital tools or systems successfully. | No |
| `TEC_5` | Outdated or incompatible technology is the current barrier to AI adoption. | **Yes** |

### Organizational Cultural Readiness

Weight: `0.1429` &nbsp;|&nbsp; Items: 4

| Column | Statement | Reverse? |
|---|---|---|
| `CUL_1` | Our organization is generally open to new technologies. | No |
| `CUL_2` | Employees are not overly resistant to changes in how they work. | No |
| `CUL_3` | Failed pilot projects are treated as learning opportunities rather than failures. | No |
| `CUL_4` | We regularly discuss innovation and new technology at a company level. | No |

### Governance, Ethics & Trust

Weight: `0.1429` &nbsp;|&nbsp; Items: 5

| Column | Statement | Reverse? |
|---|---|---|
| `GOV_1` | We are confident in our ability to manage data privacy and security if we adopted AI. | No |
| `GOV_2` | We are aware of ethical issues (e.g. bias, transparency) associated with AI tools. | No |
| `GOV_3` | We already have clear accountability and oversight structures in technology-related decisions. | No |
| `GOV_4` | We generally trust AI tools to produce accurate and fair results. | No |
| `GOV_5` | We would struggle to comply with data privacy or security regulations if we adopt AI tools. | **Yes** |
