import os


def read_disk_image(image_path):
    """
    디스크 이미지 파일을 바이너리 모드로 읽어 전체 바이트 데이터를 반환하는 함수.
    """
    with open(image_path, "rb") as f:
        return f.read()


def load_file_signatures():
    """
    복구 대상 파일 형식의 시작 시그니처와 종료 시그니처를 정의하여 반환하는 함수.
    현재는 JPG와 PDF만 대상으로 한다.
    """
    return {
        "jpg": {
            "start": b"\xFF\xD8\xFF",
            "end": b"\xFF\xD9"
        },
        "pdf": {
            "start": b"%PDF",
            "end": b"%%EOF"
        }
    }


def find_all_occurrences(data, pattern):
    """
    전체 바이트 데이터에서 특정 시그니처가 나타나는 모든 위치를 찾아 리스트로 반환하는 함수.
    """
    positions = []
    start = 0

    while True:
        idx = data.find(pattern, start)
        if idx == -1:
            break
        positions.append(idx)
        start = idx + 1

    return positions


def find_file_end(data, start_offset, file_type, signatures):
    """
    파일 시작 위치 이후에서 파일 형식에 맞는 종료 시그니처를 찾아
    파일의 끝 위치를 반환하는 함수.
    """
    end_sig = signatures[file_type]["end"]
    search_start = start_offset + len(signatures[file_type]["start"])
    end_idx = data.find(end_sig, search_start)

    if end_idx == -1:
        return None

    end_offset = end_idx + len(end_sig)

    if file_type == "pdf":
        while end_offset < len(data) and data[end_offset:end_offset + 1] in (b"\r", b"\n", b" ", b"\t"):
            end_offset += 1

    return end_offset


def parse_deleted_files(data, signatures):
    """
    디스크 이미지 전체를 순회하면서 파일 시그니처를 검색하고,
    삭제 파일 후보의 시작 위치, 끝 위치, 크기, 형식을 파싱하는 함수.
    """
    results = []

    for file_type in signatures:
        start_sig = signatures[file_type]["start"]
        start_positions = find_all_occurrences(data, start_sig)

        for start_offset in start_positions:
            end_offset = find_file_end(data, start_offset, file_type, signatures)

            if end_offset is None:
                continue

            results.append({
                "type": file_type,
                "start_offset": start_offset,
                "end_offset": end_offset,
                "size": end_offset - start_offset
            })

    return results


def save_parsed_files(data, results, output_dir):
    """
    파싱된 파일 구간을 실제 파일로 저장하는 함수.
    저장된 파일명과 경로를 결과 정보에 추가하여 반환한다.
    """
    os.makedirs(output_dir, exist_ok=True)

    counters = {}
    saved_results = []

    for item in results:
        file_type = item["type"]
        counters[file_type] = counters.get(file_type, 0) + 1

        filename = f"recovered_{file_type}_{counters[file_type]:03d}.{file_type}"
        save_path = os.path.join(output_dir, filename)

        file_bytes = data[item["start_offset"]:item["end_offset"]]

        with open(save_path, "wb") as f:
            f.write(file_bytes)

        new_item = item.copy()
        new_item["filename"] = filename
        new_item["path"] = save_path
        saved_results.append(new_item)

    return saved_results


def write_report(results, output_dir):
    """
    파싱 결과를 텍스트 파일로 저장하는 함수.
    파일 형식, 시작 위치, 끝 위치, 크기, 저장 파일명을 기록한다.
    """
    report_path = os.path.join(output_dir, "report.txt")

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("Deleted File Parsing Report\n")
        f.write("=" * 70 + "\n")

        for i, item in enumerate(results, start=1):
            f.write(f"[{i}]\n")
            f.write(f"Type         : {item['type']}\n")
            f.write(f"Start Offset : {item['start_offset']}\n")
            f.write(f"End Offset   : {item['end_offset']}\n")
            f.write(f"Size         : {item['size']} bytes\n")
            f.write(f"Filename     : {item.get('filename', '-')}\n")
            f.write(f"Path         : {item.get('path', '-')}\n")
            f.write("-" * 70 + "\n")

    return report_path


def print_results(results):
    """
    최종 파싱 결과를 콘솔 화면에 출력하는 함수.
    """
    if not results:
        print("파싱된 파일이 없습니다.")
        return

    print("=" * 90)
    print(f"{'NO':<5}{'TYPE':<8}{'START':<15}{'END':<15}{'SIZE':<12}{'FILENAME'}")
    print("=" * 90)

    for i, item in enumerate(results, start=1):
        print(
            f"{i:<5}"
            f"{item['type']:<8}"
            f"{item['start_offset']:<15}"
            f"{item['end_offset']:<15}"
            f"{item['size']:<12}"
            f"{item.get('filename', '-')}"
        )

    print("=" * 90)
    print(f"총 {len(results)}개 파일 파싱 완료")


def main():
    """
    프로그램의 전체 실행 흐름을 제어하는 메인 함수.
    디스크 이미지 파일을 읽고, 삭제 파일 후보를 파싱한 뒤,
    결과 파일과 리포트를 저장한다.
    """
    image_path = input("디스크 이미지 파일 경로 입력: ").strip()
    output_dir = input("저장 폴더명 입력(기본값: recovered): ").strip()

    if not image_path:
        print("디스크 이미지 파일 경로가 비어 있습니다.")
        return

    if not os.path.exists(image_path):
        print("지정한 디스크 이미지 파일이 존재하지 않습니다.")
        return

    if not output_dir:
        output_dir = "recovered"

    print("[1] 디스크 이미지 읽는 중...")
    data = read_disk_image(image_path)

    print("[2] 파일 시그니처 불러오는 중...")
    signatures = load_file_signatures()

    print("[3] 삭제 파일 후보 파싱 중...")
    parsed_results = parse_deleted_files(data, signatures)

    print("[4] 파일 저장 중...")
    saved_results = save_parsed_files(data, parsed_results, output_dir)

    print("[5] 리포트 작성 중...")
    report_path = write_report(saved_results, output_dir)

    print("[6] 결과 출력")
    print_results(saved_results)

    print(f"리포트 저장 완료: {report_path}")


if __name__ == "__main__":
    main()