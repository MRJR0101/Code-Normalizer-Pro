# CODE Project - Week 1 Execution Plan

**Date Started**: 2026-02-12
**Path**: Solo Developer Tool (Path 1)
**Goal**: Launch package, get first 20 user conversations

---

## TODAY (Day 1) - Pre-Launch Validation ✅

### Critical Path Items
- [ ] Activate venv and run tests: `C:\Dev\PROJECTS\CODE\.venv\Scripts\activate; python -m pytest -q`
- [ ] Validate package locally: `pip install -e .`
- [ ] Test CLI smoke test: `code-normalizer-pro --help`
- [ ] Review and finalize outreach posts
- [ ] Set up TestPyPI account (if needed)

### Commands to Run
```powershell
# Activate virtual environment
Set-Location C:\Dev\PROJECTS\CODE
.\.venv\Scripts\Activate.ps1

# Run tests
python -m pytest -q

# Install package locally in editable mode
pip install -e .

# Test CLI
code-normalizer-pro --help
code-normalizer-pro . --dry-run

# Check package build
python -m twine check dist/*
```

---

## Day 2 - TestPyPI Release

### Tasks
- [ ] Upload to TestPyPI: `python -m twine upload --repository testpypi dist/*`
- [ ] Create fresh test venv
- [ ] Install from TestPyPI: `pip install -i https://test.pypi.org/simple/ code-normalizer-pro`
- [ ] Run smoke tests on TestPyPI version
- [ ] Document any installation issues

### Success Criteria
- Package installs without errors
- CLI command works: `code-normalizer-pro --help`
- Basic normalization works on test directory

---

## Day 3 - Official PyPI Release

### Tasks
- [ ] Upload to PyPI: `python -m twine upload dist/*`
- [ ] Verify package page: https://pypi.org/project/code-normalizer-pro/
- [ ] Test installation: `pip install code-normalizer-pro`
- [ ] Create GitHub repository (if not exists)
- [ ] Tag release: `git tag v3.0.1-alpha.1`
- [ ] Push tags: `git push --tags`

### Post-Release
- [ ] Update CHANGELOG.md with release date
- [ ] Take screenshots for outreach posts
- [ ] Prepare demo GIFs (optional but recommended)

---

## Day 4 - Dev.to Launch Post

### Tasks
- [ ] Write full Dev.to article based on outline
- [ ] Include installation, demo, CI integration example
- [ ] Post article and monitor comments
- [ ] Log all engaged users in `docs/launch/first_100_users.csv`

### Metrics Target
- 5+ meaningful comments/questions
- 2+ users try the tool

---

## Day 5 - Hacker News Launch

### Tasks
- [ ] Post Show HN using template
- [ ] Monitor thread actively for first 4 hours
- [ ] Respond to every comment within 30 minutes
- [ ] Log all users who express interest

### Success Criteria
- Stay on front page for 2+ hours
- 10+ comments
- 3+ users report trying it

---

## Day 6 - Reddit Launch

### Target Subreddits
- r/Python or r/programming

### Tasks
- [ ] Post using Reddit template
- [ ] Engage with all comments
- [ ] Log feedback and pain points

---

## Day 7 - Follow-ups & Weekly Review

### Tasks
- [ ] Follow up with all interested users
- [ ] Run metrics: `python scripts/launch_metrics.py`
- [ ] Run feedback prioritizer: `python scripts/feedback_prioritizer.py`
- [ ] Plan Week 2 based on feedback

### Success Criteria for Week 1
- [ ] 20+ user conversations logged
- [ ] 5+ users actively trying the tool
- [ ] 3+ clear pain points identified
- [ ] Package has 50+ downloads

---

## Tracking Commands

### Daily
```powershell
Set-Location C:\Dev\PROJECTS\CODE
python scripts/launch_metrics.py
```

### Weekly
```powershell
python scripts/feedback_prioritizer.py
python scripts/sales_pipeline_metrics.py
```
