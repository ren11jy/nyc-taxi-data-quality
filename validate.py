import argparse
import json
import sqlite3
import sys
from pathlib import Path

import great_expectations as gx
import pandas as pd


DATA_URL = (
    "https://raw.githubusercontent.com/great-expectations/"
    "gx_tutorials/main/data/yellow_tripdata_sample_2019-01.csv"
)
DATA_FILE = Path("data/yellow_tripdata_sample_2019-01.csv")
REPORT_DIR = Path("reports")
DATABASE_FILE = Path("data/validated_taxi.sqlite")


def load_data() -> pd.DataFrame:
    DATA_FILE.parent.mkdir(exist_ok=True)
    if DATA_FILE.exists():
        print(f"读取本地数据：{DATA_FILE}")
        return pd.read_csv(DATA_FILE)

    print("首次运行，正在下载 GX 官方出租车样例数据……")
    df = pd.read_csv(DATA_URL)
    df.to_csv(DATA_FILE, index=False)
    print(f"已保存到：{DATA_FILE}")
    return df


def validate(df: pd.DataFrame):
    context = gx.get_context(mode="ephemeral")
    source = context.data_sources.add_pandas(name="taxi_source")
    asset = source.add_dataframe_asset(name="yellow_taxi_trips")
    batch_definition = asset.add_batch_definition_whole_dataframe("all_rows")

    suite = gx.ExpectationSuite(name="taxi_quality_rules")
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToNotBeNull(column="pickup_datetime")
    )
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToNotBeNull(column="dropoff_datetime")
    )
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToBeBetween(
            column="trip_distance", min_value=0
        )
    )
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToBeBetween(
            column="passenger_count", min_value=1, max_value=6
        )
    )
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToNotBeNull(
            column="trip_duration_minutes"
        )
    )
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToBeBetween(
            column="trip_duration_minutes", min_value=0
        )
    )
    context.suites.add(suite)

    definition = gx.ValidationDefinition(
        name="validate_taxi_batch", data=batch_definition, suite=suite
    )
    context.validation_definitions.add(definition)
    checkpoint = gx.Checkpoint(
        name="taxi_checkpoint", validation_definitions=[definition]
    )
    context.checkpoints.add(checkpoint)
    return checkpoint.run(batch_parameters={"dataframe": df})


def find_invalid_rows(df: pd.DataFrame) -> pd.DataFrame:
    problems = pd.DataFrame(
        {
            "pickup_datetime_missing": df["pickup_datetime"].isna(),
            "dropoff_datetime_missing": df["dropoff_datetime"].isna(),
            "negative_distance": df["trip_distance"] < 0,
            "invalid_passenger_count": ~df["passenger_count"].between(1, 6),
            "duration_missing": df["trip_duration_minutes"].isna(),
            "negative_duration": df["trip_duration_minutes"] < 0,
        },
        index=df.index,
    )
    invalid = df.loc[problems.any(axis=1)].copy()
    invalid["failure_reason"] = problems.loc[invalid.index].apply(
        lambda row: ", ".join(row.index[row]), axis=1
    )
    return invalid


def main() -> int:
    parser = argparse.ArgumentParser()
    error_group = parser.add_mutually_exclusive_group()
    error_group.add_argument(
        "--inject-error",
        action="store_true",
        help="故意把第一行行程距离改成负数，演示校验失败",
    )
    error_group.add_argument(
        "--inject-time-error",
        action="store_true",
        help="故意把第一行下车时间改成早于上车时间",
    )
    args = parser.parse_args()

    try:
        df = load_data()
        if args.inject_error:
            df.loc[df.index[0], "trip_distance"] = -1
            print("已注入异常：第一行 trip_distance = -1")
        if args.inject_time_error:
            pickup = pd.to_datetime(df.loc[df.index[0], "pickup_datetime"])
            df.loc[df.index[0], "dropoff_datetime"] = (
                pickup - pd.Timedelta(minutes=1)
            ).strftime("%Y-%m-%d %H:%M:%S")
            print("已注入异常：第一行下车时间早于上车时间")

        pickup_times = pd.to_datetime(df["pickup_datetime"], errors="coerce")
        dropoff_times = pd.to_datetime(df["dropoff_datetime"], errors="coerce")
        df["trip_duration_minutes"] = (
            dropoff_times - pickup_times
        ).dt.total_seconds() / 60

        result = validate(df)
        REPORT_DIR.mkdir(exist_ok=True)
        report_name = (
            "invalid_time.json"
            if args.inject_time_error
            else "invalid.json" if args.inject_error else "normal.json"
        )
        report_path = REPORT_DIR / report_name
        report = {
            "source": str(DATA_FILE),
            "rows": len(df),
            "injected_error": args.inject_error or args.inject_time_error,
            "success": bool(result.success),
            "validations": [
                validation.to_json_dict()
                for validation in result.run_results.values()
            ],
        }
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        if result.success:
            DATABASE_FILE.parent.mkdir(exist_ok=True)
            with sqlite3.connect(DATABASE_FILE) as connection:
                df.to_sql(
                    "validated_trips", connection, if_exists="replace", index=False
                )
            print(f"通过校验，已写入数据库：{DATABASE_FILE}")
        else:
            invalid_rows = find_invalid_rows(df)
            invalid_path = REPORT_DIR / report_name.replace(".json", "_rows.csv")
            invalid_rows.to_csv(invalid_path, index=False)
            print(f"校验失败，未写入数据库；异常行：{invalid_path}")

        print(f"数据行数：{len(df):,}")
        print(f"校验结果：{'通过' if result.success else '失败'}")
        print(f"报告位置：{report_path}")
        print(result.describe())
        return 0 if result.success else 1
    except Exception as exc:
        print(f"运行出错：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
