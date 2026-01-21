# AI Agent Flow Diagram - Internal Product Name Generation

## Complete System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    MENU SCRAPING PIPELINE                        │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                scraper_agent.py (Main Entry)                    │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │   Error Monitor │  │   Auto-Fixer    │  │  Claude AI Fix  │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      main.py (Core Scraper)                    │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │  Data Scraping  │  │ Data Processing │  │  Database Save  │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                INTERNAL NAME GENERATION FLOW                    │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│           internal_name_orchestrator.py (Gatekeeper)            │
│                                                                 │
│  Product Dictionary Entry:                                      │
│  {                                                              │
│    "Product name": "Rhize Animal Face 1g Pre Roll",             │
│    "Internal Product Name": ""  ← EMPTY?                        │
│  }                                                              │
│                                                                 │
│  ┌─────────────────┐                                           │
│  │   CHECK: Has     │                                           │
│  │   Internal Name? │                                           │
│  └─────────────────┘                                           │
│           │                                                     │
│    ┌──────┴──────┐                                               │
│    │             │                                               │
│    ▼             ▼                                               │
│  YES           NO                                               │
│    │             │                                               │
│    ▼             ▼                                               │
│  RETURN        CALL AI                                           │
│  PRODUCT      AGENT                                             │
│                │                                               │
│                ▼                                               │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                AI Agent - Name Generation Pipeline              │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 1: ai_extract_internal_name()                            │
│                                                                 │
│  Input: "Rhize Animal Face 1g Pre Roll"                        │
│                                                                 │
│  ┌─────────────────┐                                           │
│  │   Claude API     │                                           │
│  │   Call           │                                           │
│  └─────────────────┘                                           │
│           │                                                     │
│           ▼                                                     │
│  ┌─────────────────┐                                           │
│  │   AI Response   │                                           │
│  │   {                                      │                   │
│  │     "internal_product_name": "Animal Face",                  │
│  │     "confidence": 0.92                                        │
│  │   }                                      │                   │
│  └─────────────────┘                                           │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 2: Basic Validation Gate                                   │
│                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │   Name exists?  │  │  Confidence ≥   │  │  Length ≥ 3?    │ │
│  │                 │  │     0.85?       │  │                 │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
│           │                     │                     │        │
│           ▼                     ▼                     ▼        │
│         REJECT                REJECT                REJECT      │
│           │                     │                     │        │
│           └─────────┬───────────┴─────────┬───────────┘        │
│                     │                   │                    │
│                     ▼                   ▼                    │
│                 CONTINUE            CONTINUE                 │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 3: Quality Validation (name_validation.py)                │
│                                                                 │
│  Input: "Animal Face", confidence: 0.92                        │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │              QUALITY SCORING ENGINE                          │ │
│  │                                                             │ │
│  │  ┌─────────────────┐  ┌─────────────────┐                  │ │
│  │  │ Brand Check     │  │ Product Type    │                  │ │
│  │  │ (-0.8 penalty)  │  │ Check (-0.5)    │                  │ │
│  │  └─────────────────┘  └─────────────────┘                  │ │
│  │                                                             │ │
│  │  ┌─────────────────┐  ┌─────────────────┐                  │ │
│  │  │ Quality Bonus    │  │ Format Check    │                  │ │
│  │  │ (+0.7 max)      │  │ (-0.1 penalty)  │                  │ │
│  │  └─────────────────┘  └─────────────────┘                  │ │
│  │                                                             │ │
│  │  ┌─────────────────┐  ┌─────────────────┐                  │ │
│  │  │ Length Check    │  │ Duplicate       │                  │ │
│  │  │ (-0.2/-0.3)     │  │ Check (-1.0)    │                  │ │
│  │  └─────────────────┘  └─────────────────┘                  │ │
│  └─────────────────────────────────────────────────────────────┘ │
│           │                                                     │
│           ▼                                                     │
│  ┌─────────────────┐                                           │
│  │   Total Score   │  Animal Face: 0.80                        │
│  │   Calculation   │                                           │
│  └─────────────────┘                                           │
│           │                                                     │
│           ▼                                                     │
│  ┌─────────────────┐                                           │
│  │   Decision      │  ACCEPT: High Quality                     │
│  │   Engine        │                                           │
│  └─────────────────┘                                           │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 4: Pattern Management & Persistence                       │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  IF VALID:                                                     │
│                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │   Save to       │  │   Log Event     │  │ Update Memory   │ │
│  │   Patterns      │  │   History       │  │   Cache         │ │
│  │   (.json)       │  │   (.json)       │  │   (AUTO_PATTERNS)│ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
│           │                     │                     │        │
│           └─────────┬───────────┴─────────┬───────────┘        │
│                     │                   │                    │
│                     ▼                   ▼                    │
│                 SUCCESS             SUCCESS                  │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 5: Notification System                                   │
│                                                                 │
│  ┌─────────────────┐                                           │
│  │   Email         │  Subject: "New AI Product Mapping Created" │
│  │   Notification  │  Body: Original → Internal Name + Confidence│
│  │   (Gmail SMTP)  │                                           │
│  └─────────────────┘                                           │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  FINAL OUTPUT                                                  │
│                                                                 │
│  Product Dictionary Updated:                                    │
│  {                                                              │
│    "Product name": "Rhize Animal Face 1g Pre Roll",             │
│    "Internal Product Name": "Animal Face"  ← NOW FILLED!        │
│  }                                                              │
└─────────────────────────────────────────────────────────────────┘

## Decision Tree Summary

```
START: Product with empty Internal Product Name
    │
    ├─ HAS Internal Name? → YES → RETURN (skip AI)
    │
    └─ NO → CALL AI AGENT
         │
         ├─ AI returns nothing? → REJECT
         │
         ├─ AI confidence < 0.85? → REJECT
         │
         ├─ Name length < 3? → REJECT
         │
         └─ QUALITY VALIDATION
              │
              ├─ Contains brand? → REJECT
              │
              ├─ Contains product type? → REJECT
              │
              ├─ Is duplicate? → REJECT
              │
              ├─ Quality score < 0.3? → REJECT
              │
              └─ VALID → ACCEPT & SAVE
```

## Key Components

### 1. **Gatekeeper** (`internal_name_orchestrator.py`)
- Only triggers AI when `Internal Product Name` is empty
- Never modifies existing data
- Append-only pattern creation

### 2. **AI Engine** (`ai_agent.py`)
- Claude API integration (placeholder currently)
- Basic validation (confidence, length)
- Enhanced with quality validation

### 3. **Quality Validator** (`name_validation.py`)
- Brand name detection (60+ known brands)
- Product type filtering (30+ product types)
- Quality scoring based on strain indicators
- Duplicate detection against existing patterns
- Format validation (title case, length)

### 4. **Persistence Layer**
- Auto-mappings saved to `data/product_name_patterns.auto.json`
- Event history logged to `mapping_history.py`
- In-memory cache for performance

### 5. **Notification System**
- Email alerts for new AI-generated mappings
- Includes original name, generated name, confidence
- Gmail SMTP integration

## Safety Mechanisms

1. **Hard Stops**: Never modifies existing internal names
2. **Validation Gates**: Multiple quality checkpoints
3. **Append-Only**: New patterns only added, never overwritten
4. **Audit Trail**: All AI decisions logged
5. **Notifications**: Team alerted to new mappings
6. **Fallbacks**: Graceful degradation if AI fails

## Data Flow Example

```
Input: "Rhize Cannabis Company Animal Face 1g Pre Roll"
  ↓
AI Extracts: "Animal Face" (confidence: 0.92)
  ↓
Quality Score: 0.80 (brand removed, quality indicators detected)
  ↓
Adjusted Confidence: 0.74 (0.92 × 0.80)
  ↓
Decision: ACCEPT (score > 0.3, no issues)
  ↓
Save: {"animal face": "Animal Face"} to patterns
  ↓
Log: Mapping event recorded
  ↓
Notify: Email sent to team
  ↓
Output: Product updated with "Internal Product Name": "Animal Face"
```

This system ensures only high-quality, canonical internal product names are generated and persisted, with comprehensive validation and audit trails.
