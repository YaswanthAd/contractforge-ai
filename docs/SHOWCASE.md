# Showcase guide

## The story

AI can propose a migration. The hard engineering problem is knowing when that migration damages data.

## A 60–90 second recording

1. Open `docs/assets/implementation.png` and point out the deterministic domain engine and optional model boundary.
2. Start the workbench in evidence-engine mode. Show the safe migration: 8 events accepted, with cents converted to dollars and customer identity preserved.
3. Open the lossy-cast scenario: 5 events are quarantined and the release gate blocks.
4. Switch to Event replay and inspect an original payload plus its exact failure.
5. Explain where local AI enters, what is validated, and how the app falls back when inference fails.
6. Close with one tradeoff: a passing finite replay is evidence, not proof of universal compatibility.

## Suggested post draft

Would you let an AI-generated migration touch your data before replaying it?

I’m building ContractForge, an AI-assisted data-contract lab that makes migrations prove themselves.

The first local release includes a restricted migration DSL, event-by-event replay, semantic value checks, and inspectable counterexamples. A local Ollama model can propose the migration, while deterministic checks control whether each event survives.

One synthetic scenario catches five events that would lose fractional dollar values through an integer cast.

The repo includes the running demo, an editable architecture diagram, the LLD, and tests. This is an early local release using synthetic data; production connectors and live model evaluation are next.

Which schema changes have caused the most surprising production failures for your team?

https://github.com/YaswanthAd/contractforge-ai

#DataEngineering #AIEngineering #Python

## Share honestly

Lead with the failure you can demonstrate, not broad claims about autonomous agents. Attach `docs/assets/implementation.png` and a short screen recording. Use `docs/assets/architecture.png` when discussing the proposed AWS deployment, and label it as a blueprint. Do not claim production adoption, cost savings, model accuracy, stars, or traction without measured evidence. Pin the repo on your GitHub profile after publication.
