# Capstone Project: MedGraph AI

## What You'll Build

A medication information assistant that showcases the advantages of **GraphRAG over traditional RAG** for pharmaceutical and medication-related queries.

The system will process **PDF documents about medications**, including drug leaflets, prescribing information, SPCs(medication characteristics), formularies, and interaction references. It will convert this content into structured knowledge and answer complex questions such as:

- dosage guidance from official documents
- contraindications and warnings
- drug-drug interactions
- substitution or therapeutic alternatives
- medication suitability based on patient context

---

## Learning Goals
- Implement **RAG and GraphRAG** for medical/pharmaceutical documents
- Build a **knowledge graph** from unstructured PDF data
- Design a system that answers **complex medication questions with citations**
- Add **safety guardrails** for high-stakes domains

---

## Project Overview

### Problem
Healthcare professionals and patients often struggle because medication information is:
- spread across many PDF documents
- difficult to search quickly
- full of cross-references between warnings, interactions, age groups, and dosage rules
- risky to interpret without proper source grounding

Traditional document search may retrieve relevant paragraphs, but it often fails when the question requires connecting multiple facts, for example:
- age + body mass + contraindications
- drug A + drug B + kidney impairment
- substitute medication + same active substance/class + restrictions

### Solution
Build a **GraphRAG-based medication assistant** that:
- ingests medication PDFs
- extracts entities such as:
    - drug name
    - active ingredient
    - dosage form
    - indication
    - contraindication
    - adverse effect
    - interaction
    - age restriction
    - weight-based dosing rule
    - pregnancy/lactation warning
    - substitution/alternative relationships
- stores them in a **knowledge graph**
- answers user questions with:
    - grounded retrieval
    - reasoning across connected medical facts
    - references to original document sections

---

## Key Queries to Support
Your system should answer questions like
- “What is the recommended dose of Drug X for a child weighing 25 kg?”
- “Can Drug A be mixed with Drug B?”
- “Which medications are contraindicated in pregnancy?”
- “What alternatives exist for Drug X with the same active ingredient?”
- “Which medications should be avoided for elderly patients?”
- “What warnings apply if the patient has liver or kidney impairment?”
- “Which drugs interact with ibuprofen?”
- “What is the difference between Drug A and Drug B?”

Important project rule:
- For dosage, substitutions, and interaction questions, the system must return **source-cited answers** and clearly state that final decisions require **doctor/pharmacist verification**.

---

## Deliverables
- Natural language medication query interface 
- PDF ingestion pipeline for medication documents
- Knowledge graph extracted from pharmaceutical texts
- GraphRAG query engine
- Naive RAG baseline for comparison
- Evaluation report showing where GraphRAG performs better
- Demo application with citations and safety notices

---

## Success Criteria

### Minimum Requirements

- Extract knowledge graph from **30+ medication PDFs**
- Identify and store key medical/pharmaceutical entities and relationships
- Answer at least **10 medication intelligence queries correctly**
- Demonstrate **GraphRAG superiority** on multi-hop questions
- Provide document-grounded answers with citations
- Complete technical documentation and demo

### Advanced Features (Bonus)
- Drug interaction graph visualization
- Patient profile input:
    - age
    - weight
    - pregnancy status
    - kidney/liver impairment
- Explainable answers with highlighted evidence
- Multilingual PDF support
- Confidence scoring and safety-risk classification
- Dashboard for exploring medication relationships
- Detection of conflicting information across sources

---

## Core Use Cases to Solve

System should handle these realistic scenarios:

### Dosage Guidance

“What dose of Drug X is described for a patient aged 8 years and weighing 30 kg?”

### Interaction Check

“Can Drug A and Drug B be taken together?”

### Contraindication Search

“Which medications should be avoided during pregnancy?”

### Substitution Support

“What can be used as an alternative to Drug X?”

### Safety Screening

“What warnings apply to this medication for elderly patients?”

### Multi-Hop Clinical Query

“Which pain medications are suitable for a patient with gastric ulcer risk and which should be avoided?”

---

## Getting Started

### Suggested Data Sources

Start with structured and semi-structured medication PDFs such as:

- package inserts / PILs
- SmPC / SPC documents
- drug formularies
- hospital guidelines
- interaction reference sheets


---

## Safety & Compliance Requirements

Because this is a medical domain, your system should include:

- **citation-first answers**
- clear statement that it is a **decision-support tool**, not a replacement for a clinician
- refusal or caution on unsupported/high-risk questions
- warning when evidence is missing or ambiguous
- distinction between:
    - exact source-backed information    
    - inferred or approximate reasoning
- logs for traceability of answer generation

Good rule:

> The system should never invent a dose, interaction, or substitute.  
> It should only answer from retrieved evidence or explicitly say the information was not found.

---

## Extension Areas

You can extend the system with:

- patient-profile-aware query interpretation
- ATC classification integration
- drug class reasoning
- interaction severity ranking
- explainable recommendation engine
- evidence highlighting inside PDF sections
- multilingual medication document support
- dashboard for clinicians or pharmacists

---

## Final Goal

Build a professional **AI medication knowledge system** that solves a real-world healthcare information problem while demonstrating advanced **GraphRAG techniques**, retrieval quality, and safe AI design.

This can become a very strong portfolio project because it shows:
- LLM application in a high-stakes domain
- graph-based reasoning
- document intelligence
- evaluation discipline
- practical system design with safety considerations
