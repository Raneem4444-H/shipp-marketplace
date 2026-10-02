# SHIPP Marketplace

**Databricks Data Engineering + AI Capstone**

SHIPP is a two-sided household-item marketplace connecting people who have
useful household items with people who need them.

The project demonstrates one complete Data + AI workflow:

**Business Event → Operational Data → Incremental Processing → Trusted Matching →
Semantic Retrieval → AI-Assisted Recommendation → Approved Operational Action**

---

<h2 align="center">🎬 SHIPP Repository & Architecture Video Tour</h2>

<p align="center">
  <a href="https://gitdiagram.com/raneem4444-h/shipp-marketplace/video">
    <img
      src="https://gitdiagram.com/video-badge.svg"
      alt="Watch the SHIPP one-minute repository and architecture video tour"
      width="700"
    />
  </a>
</p>

<p align="center">
  <strong>
    Watch the one-minute visual tour of SHIPP's architecture, repository,
    data pipeline, RAG/Search components, and AI Agent implementation.
  </strong>
</p>

---

## 🗺️ Explore the Interactive Repository Architecture

The interactive GitDiagram provides a file-level view of how SHIPP's
implementation is organized across the Spark pipeline, RAG/Search layer,
AI Agent, Lakebase integration, and shared configuration.

### [Open the interactive SHIPP GitDiagram →](https://gitdiagram.com/raneem4444-h/shipp-marketplace)

> **Architecture note:**  
> The SHIPP business/data-flow diagrams in this README define the authoritative
> system architecture. GitDiagram complements them by showing repository and
> code relationships inferred from the implementation.

---

## Business Problem

Useful household items are often available at the same time that other people
nearby need them, but finding a suitable match requires more than simple
keyword search.

A useful recommendation must determine whether an item is available,
category-compatible, timely, geographically practical, and supported by
relevant listing text and image-derived context.

SHIPP combines operational marketplace data, Spark processing,
OpenRouteService enrichment, unstructured listing content,
Databricks AI Search, and a controlled AI Agent workflow.

---

## Core Business Workflow

```text
Donor creates Listing                         Requester creates Request
        │                                              │
        └──────────────────────┬───────────────────────┘
                               ↓
                            Lakebase
                       Operational Truth
                               ↓
                      Incremental Capture
                               ↓
                         Bronze → Silver
                               │
                 ┌─────────────┴─────────────────┐
                 │                               │
        MATCHING PIPELINE              CONTENT / SEARCH PIPELINE
                 │                               │
        Business Eligibility              Listing text + images
                 ↓                               ↓
          Candidate Pairs                Vision / text processing
                 ↓                               ↓
        OpenRouteService               Silver Listing Content
                 ↓                               ↓
          Silver Routes                Gold Search Documents
                 ↓                               ↓
          Gold Scoring                 Databricks AI Search
                 ↓                               │
     Gold Candidate Matches                      │
                 │                               │
                 └──────────────┬────────────────┘
                                ↓
                             AI Agent
                 trusted ranking + semantic context
                                ↓
                    Grounded Recommendation
                                ↓
                         propose_save()
                                ↓
                          User Approval
                                ↓
                         confirm_save()
                                ↓
                Revalidate Gold candidate
                   + current Lakebase state
                                ↓
                          save_item()
                                ↓
                            Lakebase
                  saved_items + agent_activity
                                ↓
                    Analytics / App Feedback
        
```