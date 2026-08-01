# ToeStub external distribution

Standalone downloadable product for partners and agent hosts:

**https://github.com/RogueGringo/ToeStub**

Local clone (dev machine): `C:\PRIMEdEV-1\ToeStub`

## What ships there

- Windows **`menu.bat`** + **`cfg/toestub.ini`**
- Job OS kernel (`realm/job_os` + dynamical topology + kb_geometry)
- MCP stdio server (`toestub` package)
- Fixtures, rotation example, partner audit

## What stays monorepo-only

- Dual-gate protein handoff / Crit / evolve
- Full AXiomZ zeta mold stack
- Overnight science campaigns

## Sync after monorepo Job OS changes

From ToeStub:

```powershell
powershell -File scripts\sync_from_monorepo.ps1 -Monorepo C:\PRIMEdEV-1\123abc-grok
cd C:\PRIMEdEV-1\ToeStub
# review git diff, run tests, commit, push
```

## End-user install

```bat
git clone https://github.com/RogueGringo/ToeStub.git
cd ToeStub
install.bat
menu.bat
```
