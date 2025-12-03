# Quick Start Guide – Raspberry Pi MCP Server

## Get Started in 10 Minutes

This guide gets you oriented with the Raspberry Pi MCP Server documentation quickly. Choose your path below.

---

## 🤖 I'm an AI Assistant Building This

**Your Mission**: Implement Phase 1 features following the design docs

### Step 1: Read Your Primary Guide (5 min)
→ **[`phase-1-scope-matrix.md`](phase-1-scope-matrix.md)**

This document tells you:
- ✅ What to build (Must Have features)
- 📅 In what order (day-by-day sequence)
- 📏 How long it takes (effort estimates)
- 📖 Where to find details (design doc references)

### Step 2: Follow Implementation Sequence (Start Day 1)
Open phase-1-scope-matrix.md → Section 9 "Implementation Sequence"

**Day 1-2**: Project setup
- Create repo structure
- Setup pyproject.toml
- Implement AppConfig
- Start with tests!

### Step 3: Reference Design Docs as Needed
Use the "Design Document Quick Reference" table in phase-1-scope-matrix.md

**Example**: Building GPIO tools?
→ Read Doc 05 §7 (gpio namespace) + Doc 08 (device control module)

### Key Guidelines for AI
- Write tests alongside code (TDD)
- Follow JSON schemas from Doc 05 exactly
- Use Pydantic models for everything
- Check security (Doc 04) for privileged ops
- If user requests Phase 2+ feature, politely refer to scope matrix

---

## 👨‍💻 I'm a Human Developer

**Your Mission**: Understand the system and contribute

### Step 1: Get Context (5 min)
→ **[`00-executive-summary.md`](00-executive-summary.md)**

Understand:
- What we're building and why
- Architecture overview
- Key design principles
- Security model

### Step 2: Understand Scope (5 min)
→ **[`phase-1-scope-matrix.md`](phase-1-scope-matrix.md)** – Section 3 (Feature Matrix)

See what's in Phase 1 vs Phase 2+

### Step 3: Set Up Development Environment (30 min)
→ **Doc 13** ([`13-python-development-standards-and-tools.md`](13-python-development-standards-and-tools.md))

```bash
# Clone repo
git clone <repo-url>
cd RaspberryPiOS-MCP

# Setup environment
uv venv .venv
source .venv/bin/activate
uv pip install -e ".[dev]"

# Verify setup
uv run pytest
uv run ruff check src tests
```

### Step 4: Pick Your Area & Deep Dive
Use **[`document-navigator.md`](document-navigator.md)** to find relevant docs

**Examples**:
- GPIO/I2C? → Doc 08
- Security? → Doc 04
- Testing? → Doc 11
- Deployment? → Doc 12

---

## 🔧 I'm Deploying This System

**Your Mission**: Install and configure on a Raspberry Pi

### Step 1: Understand What You're Deploying (5 min)
→ **[`00-executive-summary.md`](00-executive-summary.md)** – Architecture section

Key components:
- mcp-raspi-server (non-privileged)
- raspi-ops-agent (privileged)
- Cloudflare Tunnel (optional, for internet access)

### Step 2: Follow Deployment Guide (60 min)
→ **Doc 12** ([`12-deployment-systemd-integration-and-operations-runbook.md`](12-deployment-systemd-integration-and-operations-runbook.md))

Covers:
- Prerequisites
- Installation procedure
- Systemd setup
- Cloudflare Tunnel configuration
- Operations runbook

### Step 3: Configure Your System (30 min)
→ **Doc 14** ([`14-configuration-reference-and-examples.md`](14-configuration-reference-and-examples.md))

Edit `/etc/mcp-raspi/config.yml`:
- Server listen address
- Security/OAuth settings
- GPIO/I2C whitelists
- Enabled tools

### Step 4: Validate Deployment (20 min)
→ **[`acceptance-checklist.md`](acceptance-checklist.md)**

Run through checklist:
- Services running?
- Basic tools working?
- Security configured?
- Logs writing?

---

## 🔒 I'm Reviewing Security

**Your Mission**: Assess security posture

### Step 1: Read Security Model (30 min)
→ **Doc 04** ([`04-security-oauth-integration-and-access-control-design.md`](04-security-oauth-integration-and-access-control-design.md))

Covers:
- Threat model
- Authentication (Cloudflare Access/OAuth)
- Authorization (RBAC: viewer, operator, admin)
- Privilege separation (server vs agent)
- Audit logging

### Step 2: Review Attack Surface (20 min)
Key docs:
- **Doc 02** – Architecture boundaries
- **Doc 04 §7** – Security considerations
- **Doc 08** – Device control safeguards

### Step 3: Check Dangerous Operations (15 min)
→ **Doc 08** ([`08-device-control-and-reboot-shutdown-safeguards-design.md`](08-device-control-and-reboot-shutdown-safeguards-design.md))

Verify safeguards:
- GPIO/I2C whitelists
- Reboot/shutdown confirmation
- Rate limiting
- Sandbox modes for testing

### Step 4: Audit Trail Review (10 min)
→ **Doc 09** ([`09-logging-observability-and-diagnostics-design.md`](09-logging-observability-and-diagnostics-design.md))

Check:
- What's logged?
- Sensitive data masking?
- Log immutability?
- Query capabilities?

---

## 📚 I Want to Understand Everything

**Your Mission**: Comprehensive study

### Week 1: Foundation (~4 hours)
1. [`00-executive-summary.md`](00-executive-summary.md) – Overview (7 min)
2. [`01-requirements-specification.md`](01-raspberry-pi-mcp-server-requirements-specification.md) – What & why (45 min)
3. [`02-architecture-design.md`](02-raspberry-pi-mcp-server-high-level-architecture-design.md) – How (60 min)
4. [`03-platform-constraints.md`](03-raspberry-pi-platform-and-resource-constraints-design-note.md) – Pi specifics (30 min)
5. [`phase-1-scope-matrix.md`](phase-1-scope-matrix.md) – Implementation plan (45 min)

### Week 2: Core Systems (~5 hours)
6. **Doc 04** – Security (60 min)
7. **Doc 05** – Tools API (90 min)
8. **Doc 13** – Python standards (35 min)
9. **Doc 14** – Configuration (40 min)

### Week 3+: Modules & Operations (As needed)
- **Docs 06-10** – Module designs (~3-4 hours each)
- **Doc 11** – Testing (~45 min)
- **Doc 12** – Deployment (~50 min)

Use **[`document-navigator.md`](document-navigator.md)** for detailed reading paths.

---

## 🧭 Navigation Tips

### Find What You Need Fast

| I want to... | Go to... |
|--------------|----------|
| Understand the project | [`00-executive-summary.md`](00-executive-summary.md) |
| Know what to build | [`phase-1-scope-matrix.md`](phase-1-scope-matrix.md) |
| Find the right doc | [`document-navigator.md`](document-navigator.md) |
| See all tool APIs | Doc 05 (§3-9) |
| Configure the system | Doc 14 |
| Deploy to production | Doc 12 |
| Write tests | Doc 11 |
| Understand security | Doc 04 |
| Build GPIO/I2C features | Doc 08 |
| Implement self-update | Doc 10 |
| Troubleshoot issues | Doc 12 §6 (runbook) |

### Document Structure

All design docs follow this pattern:
1. **Purpose** – What this doc covers
2. **Goals/Non-Goals** – Scope
3. **Design Details** – Specifications
4. **Implementation Checklist** – Action items

### Reading Shortcuts

**For skim readers**: Read sections 1-2 (Purpose, Goals) in each doc

**For implementers**: Jump to relevant section using table of contents

**For reviewers**: Check "Implementation Checklist" at end of each doc

---

## ⚡ Next Steps by Role

### AI Assistant
1. ✅ Open [`phase-1-scope-matrix.md`](phase-1-scope-matrix.md)
2. ✅ Go to Section 9 (Implementation Sequence)
3. ✅ Start Day 1: Project setup
4. ✅ Reference design docs as you build

### Developer
1. ✅ Read [`00-executive-summary.md`](00-executive-summary.md)
2. ✅ Setup dev environment (Doc 13)
3. ✅ Pick a module (use [`document-navigator.md`](document-navigator.md))
4. ✅ Start coding with TDD

### Operator
1. ✅ Read deployment guide (Doc 12)
2. ✅ Prepare Raspberry Pi
3. ✅ Follow installation steps
4. ✅ Run acceptance checklist

### Security Reviewer
1. ✅ Read security design (Doc 04)
2. ✅ Review safeguards (Doc 08)
3. ✅ Check audit logging (Doc 09)
4. ✅ Document findings

---

## 📞 Key Resources

### Essential Documents
- **Executive Summary**: [`00-executive-summary.md`](00-executive-summary.md)
- **Scope Matrix**: [`phase-1-scope-matrix.md`](phase-1-scope-matrix.md)
- **Navigator**: [`document-navigator.md`](document-navigator.md)
- **Full Design**: Documents 01-14 in `docs/`

### External Resources
- **MCP Specification**: https://spec.modelcontextprotocol.io/
- **Raspberry Pi Docs**: https://www.raspberrypi.com/documentation/
- **Python 3.11**: https://docs.python.org/3.11/

### Support
- **Issues**: GitHub Issues (link TBD)
- **Questions**: Project discussions (link TBD)

---

## 🎯 Success Indicators

You're on the right track if:
- ✅ You understand what we're building (after reading executive summary)
- ✅ You know what's in Phase 1 (after reading scope matrix)
- ✅ You can find relevant docs quickly (using navigator)
- ✅ You're following implementation sequence (for AI/developers)
- ✅ You're validating with acceptance checklist (for ops)

**Still confused?** Go back to [`document-navigator.md`](document-navigator.md) and follow your role's reading path.

---

## 🚀 Ready to Start?

### For AI Assistants
```
→ Open: phase-1-scope-matrix.md
→ Section: 9 (Implementation Sequence)
→ Start: Day 1 tasks
→ Code: With tests!
```

### For Developers
```
→ Open: 00-executive-summary.md
→ Then: document-navigator.md (your role)
→ Setup: Dev environment (Doc 13)
→ Start: Pick a module and build
```

### For Operators
```
→ Open: Doc 12 (deployment)
→ Prepare: Raspberry Pi
→ Install: Follow steps
→ Validate: acceptance-checklist.md
```

---

**Document Version**: 1.0
**Last Updated**: 2025-12-03
**Audience**: New users (all roles)
**Time to Complete**: 10-15 minutes
