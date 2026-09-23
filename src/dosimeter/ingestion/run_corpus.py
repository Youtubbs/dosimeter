"""Run regulatory corpus ingestion."""

from .corpus import process_corpus


def main() -> None:
    results = process_corpus()

    for result in results:
        document = result["document"]

        if "error" in result:
            print(f"{document}: ERROR - {result['error']}")
            continue

        cached = result.get("cached", False)
        blocks = len(result.get("blocks", []))

        print(
            f"{document}: "
            f"cached={cached}, "
            f"blocks={blocks}"
        )


if __name__ == "__main__":
    main()