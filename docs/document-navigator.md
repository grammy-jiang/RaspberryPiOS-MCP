# Document Navigator – Reading Order & Dependencies

## Purpose

This guide helps you navigate the 14+ design documents efficiently based on your role and what you need to accomplish.

## Quick Navigation

### For AI Assistants (Start Here)
**Priority**: [`phase-1-scope-matrix.md`](phase-1-scope-matrix.md) → Implementation sequence → Reference design docs as needed

### For New Team Members
**Priority**: [`00-executive-summary.md`](00-executive-summary.md) → This navigator → Foundation docs (01-03) → Your area of interest

### For Decision Makers
**Priority**: [`00-executive-summary.md`](00-executive-summary.md) → [`01-requirements-specification.md`](01-raspberry-pi-mcp-server-requirements-specification.md)

### For Implementers
**Priority**: [`phase-1-scope-matrix.md`](phase-1-scope-matrix.md) → [`13-python-standards.md`](13-python-development-standards-and-tools.md) → Module-specific docs (06-10)

---

## Document Dependency Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    Foundation Layer                              │
│  (Read these first - everything builds on them)                 │
└─────────────────────────────────────────────────────────────────┘
                              │
         ┌────────────────────┼─────────────────────┐
         ▼                    ▼                     ▼
    ┌────────┐          ┌────────┐           ┌────────┐
    │ Doc 01 │          │ Doc 02 │           │ Doc 03 │
    │  Reqs  │──────────▶│  Arch  │───────────▶│Platform│
    └───┬────┘          └───┬────┘           └───┬────┘
        │                   │                     │
        │         ┌─────────┴─────────┐          │
        │         │                   │          │
        ▼         ▼                   ▼          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Core Design Layer                             │
│  (Read based on what you're implementing)                       │
└─────────────────────────────────────────────────────────────────┘
        │         │                   │          │
        │         ▼                   ▼          │
        │    ┌────────┐          ┌────────┐     │
        │    │ Doc 04 │          │ Doc 05 │     │
        │    │Security│◀─────────│  Tools │     │
        │    └───┬────┘          └───┬────┘     │
        │        │                   │          │
        │        │     ┌─────────────┼──────────┼─────────┐
        │        │     │             │          │         │
        ▼        ▼     ▼             ▼          ▼         ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Module Design Layer                            │
│  (Implementation details for each subsystem)                    │
└─────────────────────────────────────────────────────────────────┘
    ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐
    │ Doc 06 │  │ Doc 07 │  │ Doc 08 │  │ Doc 09 │  │ Doc 10 │
    │ System │  │Service │  │ Device │  │Logging │  │ Update │
    │Metrics │  │Process │  │Control │  │  Obs   │  │Rollback│
    └────────┘  └────────┘  └────────┘  └────────┘  └────────┘
         │           │           │           │           │
         └───────────┴───────────┴───────────┴───────────┘
                              │
         ┌────────────────────┼─────────────────────┐
         ▼                    ▼                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Implementation Layer                            │
│  (How to build, test, and deploy)                              │
└─────────────────────────────────────────────────────────────────┘
    ┌────────┐          ┌────────┐           ┌────────┐
    │ Doc 11 │          │ Doc 12 │           │ Doc 13 │
    │Testing │          │ Deploy │           │ Python │
    │Sandbox │          │Systemd │           │Standards│
    └───┬────┘          └───┬────┘           └───┬────┘
        │                   │                     │
        └───────────────────┴─────────────────────┘
                              │
                              ▼
                        ┌────────┐
                        │ Doc 14 │
                        │ Config │
                        └────────┘
```

---

## Reading Paths by Role

### Path 1: AI Assistant (Implementation Focus)

**Goal**: Understand what to build and how to build it

1. **[REQUIRED]** [`phase-1-scope-matrix.md`](phase-1-scope-matrix.md) – Your primary guide
   - What features to implement (✅ Must Have, ⚠️ Should Have, ⏭️ Phase 2+)
   - Day-by-day implementation sequence
   - Effort estimates and complexity ratings
   - Design document quick reference

2. **[As Needed]** Reference design docs based on current task:
   - **Starting project?** → Doc 02 (architecture), Doc 13 (Python standards)
   - **Implementing security?** → Doc 04 (complete security model)
   - **Building tools?** → Doc 05 (all tool interfaces), relevant module doc (06-10)
   - **Writing tests?** → Doc 11 (testing strategy)
   - **Setting up deployment?** → Doc 12 (systemd integration)

3. **[Optional]** Deep dives:
   - Doc 14 for configuration details
   - Supporting docs (test-matrix.md, acceptance-checklist.md)

### Path 2: New Developer/Team Member

**Goal**: Understand the system comprehensively

**Week 1: Foundation (3-4 hours)**
1. [`00-executive-summary.md`](00-executive-summary.md) – High-level overview (5-7 min)
2. [`01-requirements-specification.md`](01-raspberry-pi-mcp-server-requirements-specification.md) – What and why (30-45 min)
3. [`02-architecture-design.md`](02-raspberry-pi-mcp-server-high-level-architecture-design.md) – How it works (45-60 min)
4. [`03-platform-constraints.md`](03-raspberry-pi-platform-and-resource-constraints-design-note.md) – Raspberry Pi specifics (20-30 min)
5. [`phase-1-scope-matrix.md`](phase-1-scope-matrix.md) – What we're building first (30-45 min)

**Week 2: Core Systems (4-6 hours)**
6. [`04-security-design.md`](04-security-oauth-integration-and-access-control-design.md) – Security model (45-60 min)
7. [`05-tools-specification.md`](05-mcp-tools-interface-and-json-schema-specification.md) – Complete API (60-90 min)
8. [`13-python-standards.md`](13-python-development-standards-and-tools.md) – How we code (30-45 min)
9. [`14-configuration-reference.md`](14-configuration-reference-and-examples.md) – Configuration system (30-45 min)

**Week 3+: Specialized Modules (As Needed)**
- Pick modules relevant to your work (Docs 06-10)
- Read testing strategy (Doc 11) when writing tests
- Read deployment guide (Doc 12) when deploying

### Path 3: Operations/SRE

**Goal**: Deploy, configure, and maintain the system

1. [`00-executive-summary.md`](00-executive-summary.md) – Context (5-7 min)
2. [`12-deployment-runbook.md`](12-deployment-systemd-integration-and-operations-runbook.md) – **PRIMARY DOC** (60-90 min)
   - Installation procedures
   - Systemd integration
   - Cloudflare Tunnel setup
   - Troubleshooting guide
3. [`14-configuration-reference.md`](14-configuration-reference-and-examples.md) – Configuration options (30-45 min)
4. [`04-security-design.md`](04-security-oauth-integration-and-access-control-design.md) – Security considerations (45-60 min)
5. [`acceptance-checklist.md`](acceptance-checklist.md) – Validation checklist (15-20 min)
6. **As needed**: Module docs (06-10) for troubleshooting specific features

### Path 4: Security Reviewer

**Goal**: Assess security posture and identify risks

1. [`00-executive-summary.md`](00-executive-summary.md) – Context (5-7 min)
2. [`04-security-design.md`](04-security-oauth-integration-and-access-control-design.md) – **PRIMARY DOC** (60-90 min)
   - Threat model
   - Authentication & authorization
   - Privilege separation
   - Audit logging
3. [`02-architecture-design.md`](02-raspberry-pi-mcp-server-high-level-architecture-design.md) – System boundaries (30-45 min)
4. [`08-device-control-safeguards.md`](08-device-control-and-reboot-shutdown-safeguards-design.md) – Dangerous operation controls (30-45 min)
5. [`09-logging-diagnostics.md`](09-logging-observability-and-diagnostics-design.md) – Audit trail (20-30 min)
6. [`10-self-update-rollback.md`](10-self-update-mechanism-and-rollback-strategy-design.md) – Update security (30-45 min)

### Path 5: Hardware Engineer/Maker

**Goal**: Understand device control capabilities

1. [`00-executive-summary.md`](00-executive-summary.md) – Context (5-7 min)
2. [`08-device-control-safeguards.md`](08-device-control-and-reboot-shutdown-safeguards-design.md) – **PRIMARY DOC** (45-60 min)
   - GPIO control (pins, PWM, whitelists)
   - I2C operations (bus scan, read/write)
   - Camera capture
   - Safety mechanisms
3. [`05-tools-specification.md`](05-mcp-tools-interface-and-json-schema-specification.md) – API details (focus on §7) (20-30 min)
4. [`14-configuration-reference.md`](14-configuration-reference-and-examples.md) – GPIO/I2C config (focus on §8) (15-20 min)
5. **Optional**: Doc 03 for platform-specific constraints

---

## Document Reference Matrix

| When you need to... | Read these documents... | Priority |
|---------------------|------------------------|----------|
| **Understand the project** | 00, 01, 02 | High |
| **Implement features** | phase-1-scope-matrix, 02, 05, 13 | High |
| **Build specific modules** | 06 (system), 07 (service), 08 (device), 09 (logging), 10 (update) | Medium |
| **Set up security** | 04, 05 (ToolContext) | High |
| **Write tests** | 11, 13 | High |
| **Deploy to production** | 12, 14, acceptance-checklist | High |
| **Configure the server** | 14, 04 (security), 08 (devices) | High |
| **Troubleshoot issues** | 12 (runbook), 09 (diagnostics) | Medium |
| **Understand resource limits** | 03 | Low |
| **Plan updates/rollback** | 10, 12 | Medium |

---

## Document Dependencies (Cross-References)

### Document 01 (Requirements)
**Depends on**: None (foundation)
**Referenced by**: All other documents

### Document 02 (Architecture)
**Depends on**: Doc 01 (requirements)
**Referenced by**: Docs 04-14 (all implementation docs)

### Document 03 (Platform)
**Depends on**: Doc 01, 02
**Referenced by**: Docs 06, 08, 10 (resource-sensitive modules)

### Document 04 (Security)
**Depends on**: Doc 01, 02
**Referenced by**: Docs 05 (ToolContext), 07 (service whitelists), 08 (device whitelists), 09 (audit), 10 (update security)

### Document 05 (Tools Interface)
**Depends on**: Doc 01, 02, 04 (security model)
**Referenced by**: Docs 06-10 (all module implementations), phase-1-scope-matrix

### Documents 06-10 (Module Designs)
**Depends on**: Docs 01, 02, 04, 05
**Referenced by**: Doc 11 (testing), Doc 12 (deployment)

### Document 11 (Testing)
**Depends on**: Docs 01-10 (all functional docs)
**Referenced by**: phase-1-scope-matrix (test requirements)

### Document 12 (Deployment)
**Depends on**: Docs 01-11 (complete system)
**Referenced by**: acceptance-checklist

### Document 13 (Python Standards)
**Depends on**: Doc 02 (architecture decisions)
**Referenced by**: All implementation activities

### Document 14 (Configuration)
**Depends on**: Docs 02, 04-10 (all configurable aspects)
**Referenced by**: All implementation and deployment activities

---

## Reading Time Estimates

| Document | Pages | Reading Time | Audience |
|----------|-------|--------------|----------|
| **00-executive-summary** | 2 | 5-7 min | Everyone |
| **phase-1-scope-matrix** | 11 | 30-45 min | AI assistants, implementers |
| **document-navigator** (this) | 6 | 15-20 min | Everyone |
| **quick-start-guide** | 2 | 10-15 min | New users |
| **01-requirements** | 15-20 | 30-45 min | All roles |
| **02-architecture** | 20-25 | 45-60 min | Technical roles |
| **03-platform** | 8-10 | 20-30 min | Implementers |
| **04-security** | 18-22 | 45-60 min | Security, implementers |
| **05-tools** | 30-35 | 60-90 min | Implementers, API users |
| **06-system-metrics** | 15-18 | 30-45 min | Implementers |
| **07-service-process** | 12-15 | 30-40 min | Implementers |
| **08-device-control** | 18-22 | 45-60 min | Implementers, hardware |
| **09-logging** | 12-15 | 30-40 min | Implementers, ops |
| **10-self-update** | 20-25 | 45-60 min | Implementers, ops |
| **11-testing** | 15-18 | 35-45 min | Implementers, QA |
| **12-deployment** | 15-18 | 40-50 min | Ops, implementers |
| **13-python-standards** | 10-12 | 25-35 min | Implementers |
| **14-configuration** | 12-15 | 30-40 min | Ops, implementers |
| **test-matrix** | 2 | 5-10 min | QA, implementers |
| **acceptance-checklist** | 3 | 10-15 min | Ops, QA |
| **TOTAL** | ~250 | **10-12 hours** | Comprehensive study |

---

## Document Update History

Each document has a version and last updated date in its footer. Check these to ensure you're reading current information:

- **Foundation docs (01-03)**: Updated during requirements/architecture changes
- **Module docs (06-10)**: Updated when implementation patterns change
- **Implementation docs (11-14)**: Updated frequently during development
- **Phase 1 scope matrix**: Updated at end of each sprint or scope change
- **This navigator**: Updated when docs are added/reorganized

---

## Tips for Efficient Reading

### For First-Time Readers
1. Start with executive summary (00) – get the big picture
2. Read requirements (01) – understand the "why"
3. Read architecture (02) – understand the "how"
4. Skip to your area of interest (06-10, 12, etc.)

### For Implementers
1. **Always check phase-1-scope-matrix first** – is this feature in Phase 1?
2. Use the "Design Document Quick Reference" table in scope matrix
3. Read design docs section-by-section as you implement
4. Cross-reference Doc 05 constantly for tool interfaces

### For Reviewers
1. Check acceptance-checklist.md for validation criteria
2. Focus on module doc for area under review
3. Verify security considerations (Doc 04)
4. Check test coverage expectations (Doc 11)

### For Troubleshooters
1. Start with deployment runbook (Doc 12 §6)
2. Check logging/diagnostics design (Doc 09)
3. Review module-specific docs for detailed behavior
4. Check configuration reference (Doc 14) for misconfigurations

---

## Document Formats & Conventions

All design documents follow consistent structure:

1. **Document Purpose** – What this doc covers
2. **Goals & Non-Goals** – Scope boundaries
3. **Design Sections** – Detailed specifications
4. **Implementation Checklist** – Actionable items
5. **Cross-References** – Links to related docs

Common notation:
- `FR-N` = Functional Requirement N (from Doc 01)
- `NFR-N` = Non-Functional Requirement N (from Doc 01)
- `§N` = Section N within a document
- `Doc NN` = Reference to another document

---

## Getting Help

**If you're lost**:
1. Re-read executive summary (00) for context
2. Check this navigator for your role's reading path
3. Use the document reference matrix above
4. Ask: "What am I trying to accomplish?" then find relevant doc

**If you find inconsistencies**:
- Note the document numbers and sections
- Check document version/update dates
- Later docs override earlier ones if in conflict
- phase-1-scope-matrix is authoritative for Phase 1 features

**If you need more detail**:
- Design docs are implementation-ready but not exhaustive
- Use your judgment for reasonable implementation choices
- When uncertain, prefer safer/simpler options
- Document your decisions in code comments

---

**Document Version**: 1.0
**Last Updated**: 2025-12-03
**Maintained By**: Documentation Team
**Review Cycle**: Update when docs added/reorganized
