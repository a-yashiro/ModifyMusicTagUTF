import sys
import os
from pathlib import Path
import eyed3
import chardet
import inspect
import re
import copy

#global変数
logConvertFile = Path()
logConvertFileV1StringOver = Path()
logErrorFile = Path()
logNoTagFile = Path()
logNoTagAlbumFile = Path()
logNoTagUnknownFile = Path()
logSkipFile = Path()

cMinStringLengthAlbumPath = 10

re_title_from_filename = re.compile('^\\s*\\(.*\\)\\s*(.+)\\.mp3')
re_artist_from_filename = re.compile('^\\s*\\((.*)\\)\\s*.+\\.mp3')
re_title_from_albam_filename = re.compile('^\\s*[0-9]+\\s*[_]*(.+)\\.mp3')



#文字が全部?の場合は、そもそもCDをmp3にコンバートする際になにかエラーをおこしたファイルの可能性が高いのでチェックする
def IsAllQuestionTag ( inString ):
	if ( type(inString) is not str ):
		return False
	length = len ( inString )
	if length >= 2:
		return length == inString.count('?')
	return False

#文字列がSJISかどうかチェックし、UTF変換する
def TrySjisToUtf(inString, outString, inIsV1, outIsV1StringOver):
	outIsV1StringOver[0] = False
	#コメントタグの場合は型変換
	if type(inString) == eyed3.id3.tag.CommentsAccessor:
		if len(inString) != 0:
			inString = inString[0].text

	if ( type(inString) is not str ):
		return False
	is_utf = True
	try:
		# 判定文字コードがasciiだったら何もしない、utf8は怪しいのでLatin>CP932の変換で例外チェック
		if chardet.detect(bytes(inString,"utf-8"))["encoding"] != "ascii":
			if bytes(inString,"latin1").decode("cp932"):
				is_utf = False
	except:
		# V1バージョンの場合、文字列長がたりなくて、SJISの上位ビット文字だけ書かれているケースがある
		# その場合、文字列末端の1byteをカットして変換できるか念のため試しておく
		if inIsV1:
			raw_bytes = bytes(inString,"latin1")
			if len(inString) == 30 and len(raw_bytes) == 30:
				inString = inString[:-1]
				res = TrySjisToUtf(inString, outString, False, outIsV1StringOver)
				if res:
					outIsV1StringOver[0] = True
					return True
		#Latin1に変換できなかったならUTF8とみなしてそのまま
		return False
	if not is_utf:
		utf_string = bytes(inString,"latin1").decode("cp932")
		#print("find cp932:"+str(member)+"["+str(inString)+"]")
		#print(str(member) + ":" +utf_string)

		#もともとの文字列長と、CP932に変換した文字列長が同じだったら変換しない
		if len(inString) != len(utf_string):
			outString[0] = copy.copy(utf_string)
			return True
	#変換できなかった
	return False

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



#eyed3が処理できてないことがあるのでID3v1タグを自前処理するクラス
class MyID3V1:
	"""ID3v1 tag class with binary loader."""
	
	def __init__(self,inFile):
		self.isV1TagLoaded = False
		self.filePath = inFile

		f_handle = open(self.filePath,'rb')
		binary_data = f_handle.read()
		data_size = len(binary_data)
		tag_offset = data_size - 128
		f_handle.seek(tag_offset)

		# offset = 0, size=3
		self.header = f_handle.read(3)
		byte_tag = b'TAG'
		if self.header[0] is byte_tag[0] and self.header[1] is byte_tag[1] and self.header[2] is byte_tag[2]:
			# offset = 3, size=30
			self.title = f_handle.read(30).decode("latin1")
			# offset = 33, size=30
			self.artist = f_handle.read(30).decode("latin1")
			# offset = 63, size=30
			self.album = f_handle.read(30).decode("latin1")
			# offset = 93, size=4
			self.year = f_handle.read(4).decode("latin1")

			#先のトラックの有無を調べる
			# offset = 125, size=1
			f_handle.seek(tag_offset + 125)
			self.track_active = f_handle.read(1)[0] == 0

			# offset = 97, size=28 or 30
			f_handle.seek(tag_offset + 97)
			if self.track_active:
				self.comment = f_handle.read(28).decode("latin1")
			else:
				self.comment = f_handle.read(30).decode("latin1")
			# offset = 126, size=1
			if self.track_active:
				f_handle.seek(tag_offset + 126)
				self.track_num = f_handle.read(1)[0]
			# offset = 127, size=1
			f_handle.seek(tag_offset + 127)
			self.genre = f_handle.read(1)[0]

			self.isV1TagLoaded = True
		f_handle.close()

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

		if tags is not None:

			#eyed3は、ID3v1からAlbum情報を読み込めていない。V1とV2が異なるケースで、変換できない文字が残ってしまう
			id3v1_tag = MyID3V1(file)

			for member, value in inspect.getmembers(tags):
				utf_string = [""]
				is_v1_string_over =[False]
				is_utf = TrySjisToUtf(value,utf_string,tags.version == eyed3.id3.ID3_V1_0 or tags.version == eyed3.id3.ID3_V1_1, is_v1_string_over)
				if is_v1_string_over[0]:
					#V1バージョンで30文字オーバーしたタグを補修した
					logConvertFileV1StringOver.write(str(file.resolve())+"\n")
					logConvertFileV1StringOver.write("\t"+str(member) + ":" +utf_string[0]+"\n")

				if is_utf:
					is_skipped = False

					try:
						#変換したタグを保存
						if not isCheckOnly:

							#コメントの場合は保存の仕方が異なる
							if type(value) == eyed3.id3.tag.CommentsAccessor:
								tags.comments.set(utf_string[0])
							else:
								setattr(tags,member,utf_string[0])
							#2.2.0のセーブは実装されていない, 1.0.0はUTFで保存するとおかしくなる
							if ( tags.version == eyed3.id3.ID3_V2_2 or tags.version == eyed3.id3.ID3_V1_0 or tags.version == eyed3.id3.ID3_V1_1):
								tags.save(encoding='utf-16', version=(2,3,0))
							else:
								tags.save(encoding='utf-16', version=tags.version)

						#ログを出力
						if is_first_tag:
							logConvertFile.write(str(file.resolve())+"\n")
							logConvertFile.write("\t"+"Tag version " + str(tags.version) + "\n" )
							is_first_tag = False
						logConvertFile.write("\t"+str(member) + ":" +utf_string[0]+"\n")
						if need_copy_album_from_artist and member is 'artist':
							logConvertFile.write("\t"+"copy artist to album"+"\n")
					#logConvertFile.write("\tstring length " +str(len(value))+">"+str(len(utf_string[0])) )

					except Exception as e:
						# Ascii+Latin1の場合ここに来る可能性あり
						logErrorFile.write(str(file.resolve())+"\n")
						logErrorFile.write("\tno converted utf id3 tag save error" +"\n")
						logErrorFile.write("\t" + str(e) +"\n")
				else:
					# エラーケース
					if IsAllQuestionTag(value):
						is_skipped = False
						logErrorFile.write(str(file.resolve())+"\n")
						logErrorFile.write("\tfind all question tag" +"\n")
						logErrorFile.write("\t"+str(member) + ":" +value+"\n")

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
		logConvertFileV1StringOver= (outLogPath / "logConvertFileV1StringOver.txt").open(mode='w', encoding='UTF-8')
		logConvertFileV1StringOver.write("cp932 tag convert but V1 string length over file list\n\n")
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
	
