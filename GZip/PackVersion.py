import gzip

def compress_text_file(input_file, output_file):
    with open(input_file, 'rt') as f_in:
        with gzip.open(output_file, 'wt', compresslevel=9) as f_out:
            for line in f_in:
                f_out.write(line)

# 指定输入文件和输出文件的路径
input_file = 'D:\\FGCQ\\code\\client\\game\\res\\versions'
output_file = 'D:\\FGCQ\\code\\client\\game\\res\\versions.txt'

# 调用函数进行文件打包
compress_text_file(input_file, output_file)
