import sys
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
logNoTagAlbumFile = Path()
logNoTagUnknownFile = Path()
logSkipFile = Path()

cMinStringLengthAlbumPath = 10

re_title_from_filename = re.compile('^\\s*\\(.*\\)\\s*(.+)\\.mp3')
re_artist_from_filename = re.compile('^\\s*\\((.*)\\)\\s*.+\\.mp3')
re_title_from_albam_filename = re.compile('^\\s*[0-9]+\\s*[_]*(.+)\\.mp3')

#そもそもID3タグがはいってないので、ファイル名からタグを作る
def CreateID3TagsFromFileName(inFile,inAudioFile,isCheckOnly):
	filename = inFile.name
	# ファイル名が (***)***.mp3の形式の場合
	if re_title_from_filename.match ( filename ):
		title = re_title_from_filename.sub('\\1', filename)
		artist = re_artist_from_filename.sub('\\1',filename)
		
		logNoTagFile.write(str(inFile.resolve())+"\n")
		logNoTagFile.write("\tArtist:"+artist + "\n\tTitle:" + title +"\n")
		
		#変換したタグを保存
		if not isCheckOnly:
			inAudioFile.initTag()
			tags = inAudioFile.tag
			tags.artist = artist
			tags.album = artist
			tags.title = title
			tags.save(encoding='utf-16', version=(2, 3, 0))
			
		return True
	#ファイル名が数字****.mp3の場合は、Albamだと思われるので、親フォルダをalbumにセットする
	elif re_title_from_albam_filename.match ( filename ):
		title = re_title_from_albam_filename.sub('\\1', filename)
		album = inFile.parent.name

		logNoTagAlbumFile.write(str(inFile.resolve())+"\n")
		logNoTagAlbumFile.write("\talbum:"+album + "\n\tTitle:" + title +"\n")
		
		#変換したタグを保存
		if not isCheckOnly:
			inAudioFile.initTag()
			tags = inAudioFile.tag
			tags.artist = album
			tags.album = album
			tags.title = title
			tags.save(encoding='utf-16', version=(2, 3, 0))
			
		return True
	# 親フォルダ名が10byte以上あったらそれがalbum or artist名とみなす
	elif len ( bytes (inFile.parent.name, 'utf8' )) >= 10:
		title = re_title_from_albam_filename.sub('\\1', filename)
		album = inFile.parent.name

		logNoTagUnknownFile.write(str(inFile.resolve())+"\n")
		logNoTagUnknownFile.write("\talbum:"+album + "\n\tTitle:" + title +"\n")
		
		#変換したタグを保存
		if not isCheckOnly:
			inAudioFile.initTag()
			tags = inAudioFile.tag
			tags.artist = album
			tags.album = album
			tags.title = title
			tags.save(encoding='utf-16', version=(2, 3, 0))
			
		return True
	else:
		logErrorFile.write(str(inFile.resolve())+"\n")
		logErrorFile.write("\tno ID3 tag but wrong file name pattern" +"\n")
		return False

#フォルダ単位で変換処理実行
def ExecTagCheck(outLogPath,inFolder,isCheckOnly):
	print( "checking folder : " + str(inFolder.name) )

	#ファイルの解析
	files_list = inFolder.glob("**/*.mp3")
	# 注意、files_listは配列ではなくGenerator

	for count,file in enumerate(files_list):
		#ログに書き込むときに暗黙のエンコード変換に失敗すると止まるのでIgnoreつけて変換しておく
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
					if not isCheckOnly:
						setattr(tags,member,utf_string)
						tags.save(encoding='utf-16', version=tags.version)

					#ログを出力
					if is_first_tag:
						logConvertFile.write(str(file.resolve())+"\n")
						logConvertFile.write("\t"+"Tag version " + str(tags.version) + "\n" )
						is_first_tag = False
					logConvertFile.write("\t"+str(member) + ":" +bytes(value,"latin1").decode("cp932")+"\n")

				except Exception as e:
					# Ascii+Latin1の場合ここに来る可能性あり
					logErrorFile.write(str(file.resolve())+"\n")
					logErrorFile.write("\tno converted utf id3 tag save error" +"\n")
					logErrorFile.write("\t" + str(e) +"\n")

		# そもそもタグが入っていないケース
		if tags is None or tags.title is None:
			#logNoTagFile.write("\t"+str(member) + ":" +bytes(value,"latin1").decode("cp932")+"\n")
			is_skipped = False
			CreateID3TagsFromFileName(file,audiofile, isCheckOnly)

		if is_skipped:
			logSkipFile.write(str(file.resolve())+"\n")

		#print("***********************")


#main
if __name__ == "__main__":
	scriptPath = Path(__file__).parent

	args = sys.argv
	if len(args) < 2:
		print(	'userge:\n ModifyMusicTagsUTF.py [log out path] [-c] [in convert folder path]\n'
			+ '[-c] check only(not save)')
	else:
		outLogPath = Path(args[1])
		if not outLogPath.exists():
			outLogPath.mkdir()

		#出力フォルダの遅延生成を完了待ち
		while True:
			if outLogPath.exists():
				break

		#ログファイル作成
		
		logConvertFile = (outLogPath / "logConvertFile.txt").open(mode='w', encoding='UTF-8')
		logConvertFile.write("cp932 tag convert file list\n\n")
		logErrorFile = (outLogPath / "logErrorFile.txt").open(mode='w', encoding='UTF-8')
		logErrorFile.write("convert error file list\n\n")
		logNoTagFile = (outLogPath / "logNoTagFiles.txt").open(mode='w', encoding='UTF-8')
		logNoTagFile.write("no tag added file list\n\n")
		logNoTagAlbumFile = (outLogPath / "logNoTagAlbumFile.txt").open(mode='w', encoding='UTF-8')
		logNoTagAlbumFile.write("no tag added file for album folder list\n\n")
		logNoTagUnknownFile = (outLogPath / "logNoTagUnknownFile.txt").open(mode='w', encoding='UTF-8')
		logNoTagUnknownFile.write("no tag added file unknown folder list\n\n")
		logSkipFile = (outLogPath / "logSkipFile.txt").open(mode='w', encoding='UTF-8')
		logSkipFile.write("skip file list\n\n")

		isCheckOnly = False
		for count,arg in enumerate(args):
			if count > 1:
				if arg == '-c':
					isCheckOnly = True
				else:
					if os.path.exists(arg):
						ExecTagCheck(outLogPath,Path(arg),isCheckOnly)

		logConvertFile.close()
		logErrorFile.close()
		logNoTagFile.close()
	
