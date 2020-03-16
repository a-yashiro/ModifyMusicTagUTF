import sys
import os
from pathlib import Path
import eyed3
import chardet
import inspect

#global変数
logConvertFile = Path()
logErrorFile = Path()
logNoTagFile = Path()

#フォルダ単位で変換処理実行
def ExecTagCheck(outLogPath,inFolder):
	print( "checking folder : " + str(inFolder.name) )

	#ファイルの解析
	files_list = inFolder.glob("*.mp3")
	for count,file in enumerate(files_list):
		print (" checking file ["+"{:0=3}".format(count)+"] " + str(file.resolve()))

		#タグ解析
		#Invalid UFIDのエラー時々出て邪魔
		audiofile = eyed3.load(file)
		tags = audiofile.tag

		is_first_tag = True
		for member, value in inspect.getmembers(tags):
			is_utf = True
			#print(str(member+":"+str(value)))
			try:
				# 判定文字コードがasciiだったら何もしない、utf8は怪しいのでLatin>CP932の変換で例外チェック
				if chardet.detect(bytes(value,"utf-8"))["encoding"] != "ascii":
					if bytes(value,"latin1").decode("cp932"):
						is_utf = False
			except:
				is_utf = True	#Latin1に変換できなかったならUTF8とみなしてそのまま
			if is_utf != True:
				print("find cp932:"+str(member)+"["+str(value)+"]")
				print(str(member) + ":" +bytes(value,"latin1").decode("cp932"))

				#ログを出力
				if is_first_tag:
					logConvertFile.write(str(file.resolve())+"\n")
					is_first_tag = False
				logConvertFile.write("\t"+str(member) + ":" +bytes(value,"latin1").decode("cp932")+"\n")

		# そもそもタグが入っていないケース
		if tags is None or tags.title is None:
			logNoTagFile.write(str(file.resolve())+"\n")
			#logNoTagFile.write("\t"+str(member) + ":" +bytes(value,"latin1").decode("cp932")+"\n")

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

		#出力フォルダの遅延生成を完了待ち
		while True:
			if outLogPath.exists():
				break

		#ログファイル作成
		
		logConvertFile = (outLogPath / "logConvertFile.txt").open(mode='w')
		logConvertFile.write("cp932 tag convert file list\n\n")
		logErrorFile = (outLogPath / "logErrorFile.txt").open(mode='w')
		logErrorFile.write("convert error file list\n\n")
		logNoTagFile = (outLogPath / "logNoTagFiles.txt").open(mode='w')
		logNoTagFile.write("no tag added file list\n\n")

		for count,arg in enumerate(args):
			if count > 1:
				if os.path.exists(arg):
					ExecTagCheck(outLogPath,Path(arg))

		logConvertFile.close()
		logErrorFile.close()
		logNoTagFile.close()
