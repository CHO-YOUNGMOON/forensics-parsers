# forensics-parsers

빡공팟 15기 디지털 포렌식 과정에서 파일 형식과 파일시스템 구조를 공부하며 만든 파서와 복구 도구입니다.

도구가 보여주는 결과를 그대로 받아들이기보다, 어느 오프셋에 어떤 필드가 있고 그 값을 이용해 다음 구조로 어떻게 넘어가는지 직접 확인하려고 만들었습니다. 필드 위치와 읽는 순서는 직접 분석해서 정했고, 코드 구현에는 AI를 활용했습니다. 결과는 HxD로 같은 위치를 열어 대조했습니다.

## 도구 목록

| 파일 | 대상 | 내용 |
|---|---|---|
| tools/png_parser.py | PNG | 시그니처 확인, 청크 순회, 청크별 CRC 검증 |
| tools/zip_parser.py | ZIP | EOCD, Central Directory, Local File Header 순서로 파싱 |
| tools/avi_mp4_parser.py | AVI, MP4 | 형식 판별, 박스·청크 구조 출력, AVI 스트림 추출 |
| tools/fat32_parser.py | FAT32 | MBR, Boot Sector, FAT 영역, 루트 디렉터리 파일 목록 |
| tools/ntfs_gpt_parser.py | GPT, NTFS | Protective MBR, GPT 헤더·파티션 엔트리, VBR, $MFT 파일 목록 |
| tools/ntfs_deleted_finder.py | NTFS | 삭제된 MFT 레코드에서 파일 이름 추출 |
| tools/ext4_deleted_recovery.py | EXT4 | 삭제된 inode를 찾아 extent에서 데이터 블록 위치 추출 |
| tools/signature_carver.py | 디스크 이미지 | JPG, PDF 시그니처 기반 카빙과 결과 기록 |

## 구조 정리

**PNG**
첫 8바이트 시그니처(89 50 4E 47 0D 0A 1A 0A)를 확인한 뒤 청크를 차례로 읽습니다. 청크는 Length(4) + Type(4) + Data + CRC(4)로 되어 있고, Type과 Data로 CRC를 다시 계산해 저장된 값과 비교합니다.

**ZIP**
파일 끝에서 EOCD(50 4B 05 06)를 찾고, 거기 적힌 위치로 Central Directory(50 4B 01 02)를 읽습니다. 각 CD 엔트리에 있는 오프셋으로 Local File Header(50 4B 03 04)에 들어가 파일 이름, 크기, CRC를 확인합니다.

**FAT32**
MBR 446바이트 위치의 파티션 엔트리에서 시작 LBA를 얻고, Boot Sector에서 섹터 크기, 클러스터당 섹터 수, 예약 섹터 수, FAT 크기, 루트 디렉터리 클러스터를 읽습니다.
- FAT 시작 = 파티션 시작 + 예약 섹터
- Data 시작 = FAT 시작 + FAT 크기 × 2
- 클러스터 위치 = Data 시작 + (클러스터 번호 − 2) × 클러스터당 섹터 수

디렉터리 엔트리는 32바이트 단위이고, 첫 바이트가 0xE5면 삭제된 엔트리, 속성이 0x0F면 긴 파일 이름 엔트리입니다.

**GPT, NTFS**
LBA 1의 GPT 헤더(EFI PART)에서 파티션 엔트리 위치와 개수를 읽고, Basic data 파티션의 VBR로 이동합니다. VBR 0x30 위치의 $MFT 시작 클러스터로 $MFT 위치를 계산한 다음, 1024바이트 MFT 레코드의 속성을 따라가 $FILE_NAME(0x30)에서 파일 이름을 꺼냅니다.

**NTFS 삭제 파일**
MFT 레코드 0x16 위치의 플래그가 0x00이면 사용하지 않는 레코드입니다. 이런 레코드의 $FILE_NAME 속성을 읽어 삭제된 파일의 이름을 확인합니다.

**EXT4 삭제 파일**
1024 위치의 슈퍼블록에서 블록 크기와 그룹당 inode 수를 읽고, 그룹 디스크립터로 inode 테이블 위치를 찾습니다. i_dtime이 있고 링크 수가 0인 일반 파일 inode를 삭제 파일로 보고, extent 헤더(0xF30A)를 해석해 데이터가 있던 블록 번호와 길이를 출력합니다.

**AVI, MP4**
앞 12바이트로 형식을 구분합니다. AVI는 다음 청크 = 청크 시작 + 8 + 크기 + (크기 % 2)로 패딩까지 계산하고, MP4는 다음 박스 = 박스 시작 + 크기로 이동합니다. MP4에서 크기가 1이면 64비트 크기를 읽고, 0이면 상위 박스 끝까지로 봅니다.

**시그니처 카빙**
JPG(FF D8 FF ~ FF D9)와 PDF(%PDF ~ %%EOF)의 시작과 끝 사이를 잘라 저장하고, 찾은 위치와 크기를 기록합니다.

## 사용 사례

JPEG 뒤에 붙은 MP4를 추출했는데 10초 영상이 7초에서 끊긴 적이 있습니다. avi_mp4_parser.py로 박스 구조를 출력하고 HxD에서 같은 오프셋을 확인해 보니, mdat 박스의 시작 위치와 크기로 계산한 끝 지점이 실제 파일 끝보다 앞에 있었습니다. 그 뒤에 남은 데이터를 따로 분리해서 조사했습니다.

## 실행 방법

Python 3 표준 라이브러리만 사용합니다. AVI 스트림 추출에는 ffmpeg가 필요합니다.

```
python tools/png_parser.py sample.png
python tools/zip_parser.py sample.zip
python tools/avi_mp4_parser.py video.mp4
python tools/fat32_parser.py fat32.vhd
python tools/ntfs_gpt_parser.py ntfs.img
python tools/ntfs_deleted_finder.py disk.001
python tools/ext4_deleted_recovery.py ext4.bin
python tools/signature_carver.py
```

## 참고

- 과제와 실습용으로 만들어서 손상이 심한 이미지나 큰 이미지에는 예외 처리가 부족할 수 있습니다.
- ext4_deleted_recovery.py는 첫 번째 블록 그룹만 검사합니다.
- 주석은 공부하면서 적은 메모를 그대로 남겼습니다.
