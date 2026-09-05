# import csv

# import pandas as pd

# from priority_rules import classify_priority
# from similarity import TfidfSimilarityScorer

# DATASET_PATH: str = "/home/golubev.dmitriy25/datasets/itmo_hack/parsed-new_for_itmo_hack.csv"
# OUTPUT_PATH: str = "/home/golubev.dmitriy25/datasets/itmo_hack/PROCESSED-parsed-new_for_itmo_hack.csv"


# def main() -> None:
#     scorer: TfidfSimilarityScorer = TfidfSimilarityScorer()
#     print(f"Similarity backend: {type(scorer).__name__}\n")

#     with open(DATASET_PATH, encoding="utf-8") as f:
#         rows: list[dict[str, str]] = list(csv.DictReader(f))

#     result_df: pd.DataFrame = pd.DataFrame(columns=["id", "source", "title", "text", "predicted"])

#     for row in rows:
#         text: str = row["title"] + ". " + row["text"] if row["title"] != "Без заголовка" else row["text"]
#         predicted: str = classify_priority(text, source=row["source"], scorer=scorer).priority
#         result_df.loc[len(result_df)] = [row["id"], row["source"], row["title"], row["text"], predicted]

#     result_df.to_csv(OUTPUT_PATH, index=False)
#     print("обработка завершена")


# if __name__ == "__main__":
#     main()
