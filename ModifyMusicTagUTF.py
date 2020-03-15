import sys
import os
from pathlib import Path
import eyed3
import chardet

#global変数


#フォルダ単位で変換処理実行
def ExecTagCheck(outLogPath,inFolder):
	print( "checking folder : " + str(inFolder.name) )

	#ファイルの解析
	files_list = inFolder.glob("*.mp3")
	for count,file in enumerate(files_list):
		print (" checking file ["+"{:0=3}".format(count)+"] " + file.name)

		#タグ解析
		#tags = ID3(file)
		audiofile = eyed3.load(file)
		tags = audiofile.tag
		print(tags.title)
		# utf8だったらそのまま
		is_utf = True
		try:
			print(chardet.detect(bytes(tags.title,"utf-8")))
			if bytes(tags.title,"latin1"):
			#if chardet.detect(bytes(tags.title,"utf8"))["encoding"] != "utf-8":
				is_utf = False
		except:
			is_utf = True	#Latin1に変換できなかったならUTF8とみなしてそのまま
		if is_utf != True:
			print(chardet.detect(bytes(tags.title,"latin1")))
			print(bytes(tags.title,"latin1").decode("cp932"))
		else:
			print("skip")
		print("***********************")


#main
if __name__ == "__main__":
	scriptPath = Path(__file__).parent

	args = sys.argv
	if len(args) < 2:
		print(	'userge:\n ModifyMusicTagsUTF.py [log out path] [in convert folder path]')
	else:
		outLogPath = Path(args[1])
		if not outLogPath.exists():
			outLogPath.mkdir()

		for count,arg in enumerate(args):
			if count > 1:
				if os.path.exists(arg):
					ExecTagCheck(outLogPath,Path(arg))