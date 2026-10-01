# Dosimeter — Radiation Exposure Reporting Copilot

## Overview

Dosimeter is a Python-based application that helps process radiation exposure packets, retrieve relevant regulatory information, and prepare cited reports for officer review.

The system combines deterministic rules with AI agents to organize evidence and identify cases that may require human review. It supports officer decision-making rather than replacing it.

## Features

* **Packet ingestion:** Processes exposure packets and extracts relevant information.
* **Regulatory retrieval:** Searches regulatory documents and returns supporting evidence.
* **Deterministic rules engine:** Evaluates exposure information using defined rules.
* **Agent workflow:** Uses LangGraph to coordinate specialized workers and a Reviewer.
* **Cited reporting:** Produces reports grounded in retrieved regulatory sources.
* **Human review:** Supports escalation when information is insufficient or findings require further review.
* **Testing:** Includes automated tests for project components.

## Tech Stack

* Python
* LangChain and LangGraph
* Amazon Bedrock
* Amazon Bedrock Knowledge Bases
* Amazon Textract
* PostgreSQL
* Docker
* AWS

## Project Structure

* `src/dosimeter/` — Application source code
* `corpus/` — Regulatory documents used for retrieval
* `packets/` — Sample exposure packets
* `tests/` — Automated tests
* `docs/aws/` — AWS architecture and operational documentation
* `docs/database.md` — Database documentation

## Getting Started

Clone the repository and follow the project setup instructions.

```bash
git clone <repository-url>
cd dosimeter
```

Set up the Python environment and install the project dependencies according to `pyproject.toml`.

Configure the required environment variables and AWS access before running commands that use AWS services.

The CLI supports commands for submitting exposure packets, assessing exposures, viewing dossiers, and inspecting workflow traces.

## SDLC Documentation

Project planning, sprint goals, daily check-ins, retrospectives, and other Software Development Life Cycle documentation:

**[View SDLC Documentation](https://docs.google.com/document/d/1rZknp5aPXAdf3jEwQxa0n0FRyhzcI0QXPspfFIKw6zA/edit?usp=sharing)**

## Team

* **Victoria Mulugeta:** Regulatory corpus chunking, retrieval pipeline, Knowledge Base search tool, Coordinator, Equipment Worker, and Reviewer.
* **Abdulmuqsit Jimoh:** Deterministic rules engine and additional worker functionality.
* **Anthony Sherrell:** Database and platform integration, tooling, and infrastructure work.

## Important Note

Dosimeter provides regulatory evidence and structured reporting support. Final decisions and required actions remain the responsibility of the authorized officer.
