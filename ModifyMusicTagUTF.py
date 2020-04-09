﻿import sys
import os
from pathlib import Path
import eyed3
import chardet
import inspect
import re

#global変数
logConvertFile = Path()
logErrorFile = Path()
logNoTagFile = Path()
logSkipFile = Path()

re_title_from_filename = re.compile('^\\s*\\(.*\\)\\s*(.+)\\.mp3')
re_artist_from_filename = re.compile('^\\s*\\((.*)\\)\\s*.+\\.mp3')

#そもそもID3タグがはいってないので、ファイル名からタグを作る
def CreateID3TagsFromFileName(inFile):
	filename = inFile.name
	# ファイル名が (***)***.mp3の形式の場合のみ
	if re_title_from_filename.match ( filename ):
		title = re_title_from_filename.sub('\\1', filename)
		artist = re_artist_from_filename.sub('\\1',filename)
		logNoTagFile.write("\tArtist:"+artist + "\n\tTitle:" + title +"\n")
		return True
	else:
		logErrorFile.write(str(inFile.resolve())+"\n")
		logErrorFile.write("\tno ID3 tag but wrong file name pattern" +"\n")
		return False



#フォルダ単位で変換処理実行
def ExecTagCheck(outLogPath,inFolder):
	print( "checking folder : " + str(inFolder.name) )

	#ファイルの解析
	files_list = inFolder.glob("**/*.mp3")
	# 注意、files_listは配列ではなくGenerator

	for count,file in enumerate(files_list):
		print (" checking file ["+"{:0=3}".format(count)+"] " + str(file.resolve()))

		#タグ解析
		#Invalid UFIDのエラー時々出て邪魔
		audiofile = eyed3.load(file)
		tags = audiofile.tag

		is_first_tag = True
		is_skipped = True
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
			if not is_utf:
				utf_string = bytes(value,"latin1").decode("cp932")
				#print("find cp932:"+str(member)+"["+str(value)+"]")
				#print(str(member) + ":" +utf_string)

				is_skipped = False

				try:
					#変換したタグを保存
					setattr(tags,member,utf_string)
					tags.save(encoding='utf-16', version=tags.version)

					#ログを出力
					if is_first_tag:
						logConvertFile.write(str(file.resolve())+"\n")
						logConvertFile.write("\t"+"Tag version " + str(tags.version) + "\n" )
						is_first_tag = False
					logConvertFile.write("\t"+str(member) + ":" +bytes(value,"latin1").decode("cp932")+"\n")

				except:
					logErrorFile.write(str(file.resolve())+"\n")
					logErrorFile.write("\tno converted utf id3 tag save error" +"\n")

		# そもそもタグが入っていないケース
		if tags is None or tags.title is None:
			#logNoTagFile.write("\t"+str(member) + ":" +bytes(value,"latin1").decode("cp932")+"\n")
			is_skipped = False
			res = CreateID3TagsFromFileName(file)
			if res:
				logNoTagFile.write(str(file.resolve())+"\n")

		if is_skipped:
			logSkipFile.write(str(file.resolve())+"\n")

		#print("***********************")


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
		logSkipFile = (outLogPath / "logSkipFile.txt").open(mode='w')
		logSkipFile.write("skip file list\n\n")

		for count,arg in enumerate(args):
			if count > 1:
				if os.path.exists(arg):
					ExecTagCheck(outLogPath,Path(arg))

		logConvertFile.close()
		logErrorFile.close()
		logNoTagFile.close()
	
