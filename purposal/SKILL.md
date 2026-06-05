---
name: software-project-proposal
description: >-
  Draft software project proposals and Software Requirements Specifications (SRS)
  using a 20-section stakeholder-ready template. Requires discovery first: review
  project context, ask clarifying questions, and confirm with the user before
  drafting. Use when the user asks for a project proposal, SRS, scope of work,
  pre-sales document, RFP response, or requirements engineering document.
---

# Software Project Proposal

## When to Use

Apply this skill when drafting:

- Client-facing software project proposals
- Software Requirements Specifications (SRS)
- Pre-sales or internal project scoping documents
- RFP responses requiring functional scope, NFRs, timeline, and cost

## Before You Write — Discovery First

**Do not draft the proposal until discovery is complete.** Accuracy depends on understanding the project fundamentals, not on filling the template quickly.

### Step 1: Understand the project

Before asking questions or writing anything, thoroughly review all available project context:

- Read any project description, brief, RFP, README, existing docs, or codebase the user provides
- Identify the core problem, target users, business domain, and expected outcomes
- Note integrations, constraints, compliance needs, and anything that shapes scope or architecture
- Summarize your understanding back to the user in 2–4 sentences and confirm it is correct

If no project description exists, ask the user for one before proceeding.

### Step 2: Ask the user — do not assume

**Always ask clarifying questions before writing the proposal.** Do not infer or invent details that affect scope, cost, timeline, or technical direction.

Gather enough information to produce an accurate proposal. Ask about gaps such as:

- Client / organization name and proposal audience (executive vs technical)
- Business goals, success metrics, and priority outcomes
- User types, key workflows, and must-have vs nice-to-have features
- Known technical constraints, preferred stack, or existing systems to integrate with
- Team size, roles available, timeline expectations, and budget or pricing sensitivity
- Compliance, security, or regulatory requirements
- What is explicitly out of scope
- Deliverable format preferences and any sections to omit

Ask in focused batches (5–8 questions at a time) rather than one overwhelming list. Use the AskQuestion tool when available.

### Step 3: Confirm before implementation

Present a short discovery summary covering: project fundamentals, open assumptions, and proposed document scope. **Wait for user confirmation or answers before generating the full proposal.**

Only proceed to drafting when:

- Project fundamentals are understood and confirmed
- Critical unknowns are answered or explicitly accepted as TBD with user approval
- The user has confirmed they are ready for the proposal draft

## Workflow

1. **Discovery** — Follow "Before You Write" above. Review project context, ask questions, confirm understanding.
2. **Fill every applicable section** — Use the template below. Mark unknowns as TBD and list them under Assumptions & Dependencies.
3. **Tailor depth to audience** — Executives need strong Executive Summary and Objectives; technical stakeholders need Architecture, Stack, and NFRs.
4. **Call out scope boundaries** — Always include Out of Scope to prevent scope creep.
5. **Validate completeness** — Before delivering, confirm all 20 sections are addressed or explicitly marked N/A.

## Output Format

- Deliver as markdown unless the user requests another format (PDF outline, docx structure, etc.).
- Use tables for Technology Stack, Timeline, and Risk Analysis.
- Include placeholder rows in tables when specifics are unknown.
- Keep tone professional, clear, and stakeholder-friendly — bridge technical detail and business goals.

## Document Template

Use this structure for every proposal:

### 1. Cover Page

- Project Title
- Client Name / Organization
- Submitted By (Company / Team)
- Date

### 2. Table of Contents

Headings with page numbers and hyperlinks for navigation.

### 3. Executive Summary / Project Overview

- Brief description of the project
- Business goals and objectives
- Summary of proposed solution

### 4. Project Objectives

- Specific outcomes the system aims to achieve
- KPIs or measurable goals (if known)

### 5. Scope of Work

#### A. Functional Scope

Feature modules broken down by user type or system area (e.g., Customer, Admin, Vendor).

#### B. Out of Scope (Optional)

Clearly define what is not included to avoid scope creep.

### 6. Technical Approach / Solution Architecture

- High-level system architecture diagram (optional but recommended)
- Data flow or component diagrams
- Description of how the solution works at a technical level

### 7. Technology Stack

| Layer    | Technologies                |
| -------- | --------------------------- |
| Frontend | (e.g., React, Flutter)      |
| Backend  | (e.g., Node.js, Django)     |
| Database | (e.g., PostgreSQL, MongoDB) |
| Hosting  | (e.g., AWS, Azure)          |
| CI/CD    | (e.g., GitHub Actions)      |

### 8. Non-Functional Requirements (NFRs)

- Performance
- Scalability
- Security (e.g., authentication, data protection)
- Availability/Uptime
- Compliance (if applicable)

### 9. Team Composition & Roles

- List of team roles and responsibilities
- Optional: resource allocation timeline (e.g., frontend dev full-time for 6 weeks)

### 10. Project Timeline / Milestones

| Phase                 | Duration | Deliverables        |
| --------------------- | -------- | ------------------- |
| Example: UI/UX Design | 2 weeks  | Wireframes, mockups |

Include Gantt chart when useful for presentations.

### 11. Deliverables

Tangible outputs (e.g., source code, documentation, deployed app, admin panel).

### 12. Assumptions & Dependencies

- What you expect the client to provide
- 3rd party dependencies (e.g., payment gateway API access)
- Timeline assumptions

### 13. Risk Analysis & Mitigation Plan

| Risk | Impact | Likelihood | Mitigation |
| ---- | ------ | ---------- | ---------- |

### 14. Change Management Process

- How change requests will be handled
- Approval workflow
- Impact on timeline and cost

### 15. Communication & Reporting Plan

- Meeting frequency (daily standups, weekly syncs)
- Tools used (e.g., Slack, Jira, Google Meet)
- Reporting responsibilities

### 16. Testing & Quality Assurance

- Types of testing (unit, integration, UAT)
- QA process and tools
- Acceptance criteria

### 17. Deployment & Release Strategy

- Staging and production environment
- Rollout plan
- Versioning and rollback strategy

### 18. Maintenance & Support Plan

- Post-launch support (duration, scope)
- SLA or response time for bugs
- Optional: support tiers (e.g., Basic, Premium)

### 19. Cost Estimate / Pricing (Optional)

- Breakdown by deliverables, roles, or timeline
- Payment schedule/milestones

### 20. Appendices

- UI mockups
- Sample diagrams
- API documentation reference
- Legal disclaimers or contracts

## Quality Checklist

Before finalizing:

- [ ] Discovery completed — project fundamentals reviewed and confirmed with user
- [ ] Clarifying questions asked before drafting; no critical details assumed
- [ ] Executive Summary stands alone for non-technical readers
- [ ] Functional scope maps to business objectives
- [ ] Out of Scope is explicit
- [ ] NFRs are measurable where possible
- [ ] Timeline aligns with team composition
- [ ] Risks have concrete mitigations
- [ ] Assumptions and client dependencies are listed

## Context

This template bridges technical delivery and business stakeholders. Treat it as structured communication — not just a checklist. Great software starts with shared understanding across engineering, product, and client teams.
