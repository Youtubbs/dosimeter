# Contributing

This repository uses a feature-branch and pull-request workflow. The main branch is protected: direct pushes are rejected, and every change reaches main through a pull request approved by at least one other person.

## Before you start

1. Pick a card from the team board. Every piece of work maps to one to a few board cards with ID DM-##.
2. Read the card's "Done when" criteria and the team definition of done at [this google doc](https://docs.google.com/document/d/1rZknp5aPXAdf3jEwQxa0n0FRyhzcI0QXPspfFIKw6zA/edit?tab=t.0).
3. Move the card to In Progress on the board.

## Workflow

The team shares one working branch named feature. Everyone pushes their work to feature, and feature is merged into main through a pull request. There is no branch naming convention and no one-branch-per-card rule.

The commands below are plain git and work the same in Windows (PowerShell or Git Bash), macOS and Linux.

1. Switch to the feature branch and bring it up to date:

       git checkout -b feature
       git pull origin feature

2. Make your changes. Run the tests and ruff locally before committing.

3. Commit. A commit can cover one card or several. Name the cards it touches in the message, e.g.

       git commit -m "DM-03 DM-04 IMPLEMENTED"

4. Pull again before pushing, in case a teammate pushed while you were working, then push:

       git pull origin feature
       git push origin feature

   If the pull reports a merge conflict, resolve it in the listed files, then run `git add` on them and `git commit` before pushing. If you are unsure how to resolve a conflict in someone else's code, ask them first.

5. When the work on feature is ready to go to main, open a pull request from feature into main on GitHub and fill in the pull request template seen at [pull_request_template.md](/dosimeter/.github/pull_request_template.md)

6. Ask at least one other teammate to review the pull request. Fix anything they raise by committing to feature and pushing again. The pull request updates automatically.

7. Once the pull request is approved (and, once CI exists, its status checks pass), merge it into main. Do not delete the feature branch.

8. Link the merged pull request on each board card it covers and move those cards to Done.

9. After the merge, bring feature back in line with main before starting new work:

       git checkout feature
       git pull origin main
       git push origin feature

## Rules that always apply

- Never push directly to main. Branch protection rejects it.
- Never modify anything under corpus/.
- Never commit credentials, access keys, .env files or other secrets.
- Do not add a dependency that is not already pinned in pyproject.toml without the team agreeing to it first.
- A card is done when it is tested, reviewed and merged to main. Written is not done.
