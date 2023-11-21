import gzip
import sys

debug = sys.gettrace()
if debug:
    print("Debug模式\n")
    input_file = 'D:\FGCQ3\code\\client\game\\version\\versions'
    output_file = 'D:\FGCQ3\code\\client\game\\version\\versions.txt'
else:
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    print("Release模式\ninput_file: ", input_file, " output_file: ", output_file)

def compress_text_file(input_file, output_file):
    with open(input_file, 'rt') as f_in:
        with gzip.open(output_file, 'wt', compresslevel=9) as f_out:
            for line in f_in:
                f_out.write(line)

# 调用函数进行文件打包
compress_text_file(input_file, output_file)