import os
import pandas as pd


def merge_csv_files(input_folder, output_file):
    """
    指定されたフォルダ内のすべてのCSVファイルを1つにまとめます。

    Parameters:
        input_folder (str): CSVファイルが保存されているフォルダのパス。
        output_file (str): 結合後のCSVファイルの保存先パス。
    """
    # フォルダ内のファイルをリストアップ
    csv_files = [file for file in os.listdir(
        input_folder) if file.endswith('.csv')]

    # データフレームを格納するリスト
    dataframes = []

    # 各CSVファイルを読み込み、データフレームとしてリストに追加
    for file in csv_files:
        file_path = os.path.join(input_folder, file)
        try:
            df = pd.read_csv(file_path)
            dataframes.append(df)
            print(f"読み込み完了: {file}")
        except Exception as e:
            print(f"エラーが発生しました: {file} - {e}")

    # データフレームを結合
    if dataframes:
        merged_df = pd.concat(dataframes, ignore_index=True)
        # 結合結果をCSVに保存
        merged_df.to_csv(output_file, index=False)
        # merged_df[merged_df['court'].str.contains(
        #     '大高緑地')].to_csv(output_file, index=False)
        print(f"CSVファイルを結合しました: {output_file}")
    else:
        print("結合するCSVファイルが見つかりませんでした。")


# 使用例
input_folder = "./oguri"  # CSVファイルが保存されているフォルダのパス
output_file = "./output_oguri.csv"  # 出力先のCSVファイルパス

merge_csv_files(input_folder, output_file)
