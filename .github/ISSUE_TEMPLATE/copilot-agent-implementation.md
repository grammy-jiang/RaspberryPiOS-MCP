---
name: GitHub Copilot Agent Implementation Task
about: Template for implementation tasks optimized for GitHub Copilot Agent (6-hour sessions)
title: '[Phase 1] '
labels: copilot-agent, phase-1
assignees: ''
---

## 📋 Issue Description (For Human Review)

**Estimated Time**: X hours
**Complexity**: Low/Medium/High/Very High
**Dependencies**: #[issue numbers]
**Requires Hardware**: Yes/No

### Scope
[Brief description of what will be implemented in this issue]

### Deliverables
- [ ] [Deliverable 1]
- [ ] [Deliverable 2]
- [ ] [Deliverable 3]
- [ ] Unit tests with ≥85% coverage
- [ ] Integration tests (if applicable)
- [ ] Documentation updates

### Acceptance Criteria
- ✅ [Criterion 1]
- ✅ [Criterion 2]
- ✅ [Criterion 3]
- ✅ All tests pass: `uv run pytest --cov`
- ✅ Linting passes: `uv run ruff check`
- ✅ Test coverage ≥85%

### Design Documents
- [Doc XX](../docs/XX-filename.md) §Y: [Section description]

### Human Review Checklist
- [ ] Code follows design document specifications
- [ ] All acceptance criteria met
- [ ] Tests comprehensive and passing
- [ ] Coverage ≥85% on new code
- [ ] No security vulnerabilities introduced
- [ ] No Phase 2+ features added without approval
- [ ] Hardware-specific code has sandbox mode handling
- [ ] Documentation updated (if needed)

---

## 🤖 GitHub Copilot Agent Custom Prompt

**When assigning to Copilot Agent, use this as the custom prompt:**

```
You are implementing [Feature Name] for the Raspberry Pi MCP Server project.

CONTEXT:
- Project: Python 3.11+ MCP server for Raspberry Pi device management
- Design docs: docs/ directory (read thoroughly before coding)
- Standards: TDD, ≥85% test coverage, type hints, docstrings
- Tools: uv, pytest, ruff, Pydantic models
- Time limit: 5-6 hours for this issue

DESIGN DOCUMENTS TO READ:
- [List specific doc files and sections]

IMPLEMENTATION REQUIREMENTS:
[Copy deliverables and acceptance criteria from above]

EXPECTED FILE STRUCTURE:
```python
# [Paste implementation notes/code structure here]
```

DEVELOPMENT PROCESS:
1. Read all linked design documents in docs/ directory
2. Write tests FIRST (TDD approach)
3. Implement features following design specs
4. Use Python type hints, docstrings for all public functions
5. Follow docs/13-python-development-standards-and-tools.md
6. Commit frequently with conventional commit messages (feat:, fix:, test:)
7. Run `uv run pytest --cov` - must pass with ≥85% coverage
8. Run `uv run ruff check` - must pass with zero errors

WHEN COMPLETE:
- Post implementation summary to this issue
- Post test coverage report
- Highlight any deviations from design docs with rationale
- Mark ready for human review

IF STUCK OR TIME RUNNING OUT:
- Document current state and remaining work in issue comment
- Ask clarifying questions in comments
- Reference design docs for guidance

SUCCESS CRITERIA:
All acceptance criteria above must be met for this issue to be considered complete.
```

---

## 📚 References
- [Phase 1 Scope Matrix](../docs/phase-1-scope-matrix.md)
- [GitHub Copilot Agent Issue Plan](../docs/github-copilot-agent-issue-plan.md)
- [Acceptance Checklist](../docs/acceptance-checklist.md)
