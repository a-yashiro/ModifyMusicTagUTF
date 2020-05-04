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
logConvertFileV1Tag = Path()
logErrorFile = Path()
logNoTagFile = Path()
logNoTagAlbumFile = Path()
logNoTagUnknownFile = Path()
logSkipFile = Path()
logCheckAlbumError = Path()
logForceSetAlbumFile = Path()

cMinStringLengthAlbumPath = 10

re_title_from_filename = re.compile('^\\s*\\(.*\\)\\s*(.+)\\.mp3')
re_artist_from_filename = re.compile('^\\s*\\((.*)\\)\\s*.+\\.mp3')
re_title_from_albam_filename = re.compile('^\\s*([0-9]+)\\s*[_-]*(.+)\\.mp3')

re_force_set_album = re.compile('^(.+)\t(.+)$')


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
		track = re_title_from_albam_filename.sub('\\1', filename)
		title = re_title_from_albam_filename.sub('\\2', filename)

		album = inFile.parent.name

		logNoTagAlbumFile.write(str(inFile.resolve())+"\n")
		logNoTagAlbumFile.write("\talbum:"+album + "\n\tTrack:" + track + "\n\tTitle:" + title +"\n")
		
		#変換したタグを保存
		if not isCheckOnly:
			inAudioFile.initTag()
			tags = inAudioFile.tag
			tags.artist = album
			tags.album = album
			tags.title = title
			tags.track_num = track
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



#eyed3がID3v1とID3v2が混在したファイルを正しく処理できてないことがあるのでID3v1タグだけ自前で読み書きするクラス
class MyID3V1:
	"""ID3v1 tag class with binary loader."""
	
	def __init__(self,inFile):
		self.isV1TagLoaded = False
		self.filePath = inFile

		f_handle = open(self.filePath,'rb')
		self.binary_data = f_handle.read()
		self.data_size = len(self.binary_data)
		tag_offset = self.data_size - 128
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
				self.comments = f_handle.read(28).decode("latin1")
			else:
				self.comments = f_handle.read(30).decode("latin1")
			# offset = 126, size=1
			if self.track_active:
				f_handle.seek(tag_offset + 126)
				self.track_num = f_handle.read(1)[0]
			# offset = 127, size=1
			f_handle.seek(tag_offset + 127)
			self.genre = f_handle.read(1)[0]

			self.title_modified = False
			self.artist_modified = False
			self.album_modified = False
			self.comments_modified = False

			self.isV1TagLoaded = True
		f_handle.close()

	def sjis_to_utf_target(self, inTags, inAttributeName):
		utf_string = [""]

		# V2タグが存在していて変換処理が終わっている場合、V1タグを削除する
		is_exist_v2_string = False
		v2_attribute = getattr(inTags, inAttributeName)
		is_comments = type(v2_attribute) == eyed3.id3.tag.CommentsAccessor
		if is_comments:
			is_exist_v2_string = v2_attribute is not None and len(v2_attribute) > 0 and v2_attribute[0] is not None and v2_attribute[0].text is not ''
		else:
			is_exist_v2_string = v2_attribute is not None and v2_attribute is not ''
		if is_exist_v2_string:
			setattr(self, inAttributeName, '')
			setattr(self, inAttributeName+"_modified", True)
		else:
			is_v1_string_over =[False]
			if TrySjisToUtf(getattr(self, inAttributeName), utf_string, True, is_v1_string_over):
				setattr(self, inAttributeName, utf_string[0])
				setattr(self, inAttributeName+"_modified", True)
				
				#V1にだけ存在したタグはV2にもコピーしておく
				if is_comments:
					inTags.comments.set(utf_string[0])
				else:
					setattr(inTags,inAttributeName,utf_string[0])
				logConvertFile.write("\t"+inAttributeName + ":" +utf_string[0]+"\n")
				return True
		return False

	def sjis_to_utf(self, inTags):
		if not self.isV1TagLoaded:
			return False
		is_v2tag_copied = False
		# 変換候補は、title artist album comments
		is_v2tag_copied |= self.sjis_to_utf_target(inTags,"title")
		is_v2tag_copied |= self.sjis_to_utf_target(inTags,"artist")
		is_v2tag_copied |= self.sjis_to_utf_target(inTags,"album")
		is_v2tag_copied |= self.sjis_to_utf_target(inTags,"comments")

		res = self.title_modified or self.artist_modified or self.album_modified or self.comments_modified
		if res:
			logConvertFileV1Tag.write(str(self.filePath.resolve())+"\n")
			if self.title_modified:
				logConvertFileV1Tag.write("\ttitle:" +self.title+"\n")
			if self.artist_modified:
				logConvertFileV1Tag.write("\tartist:" +self.artist+"\n")
			if self.album_modified:
				logConvertFileV1Tag.write("\talbum:" +self.album+"\n")
			if self.comments_modified:
				logConvertFileV1Tag.write("\tcomments:" +self.comments+"\n")
		return is_v2tag_copied
			

	def save(self):
		if not self.isV1TagLoaded:
			return False
		if self.title_modified or self.artist_modified or self.album_modified or self.comments_modified:
			f_handle = open(self.filePath,'wb')
			if not f_handle.writable():
				return False

			tag_offset = self.data_size - 128
			wirte_buffer = bytearray(self.binary_data)
			
			if self.title_modified:
				# offset = 3, size=30
				row_string = self.title.encode('utf-8')
				row_string_length = len(row_string)
				
				for i in range(30):
					if i < row_string_length:
						wirte_buffer[tag_offset+3+i] = row_string[i]
					else:
						wirte_buffer[tag_offset+3+i] = 32
				
			if self.artist_modified:
				# offset = 33, size=30
				row_string = self.artist.encode('utf-8')
				row_string_length = len(row_string)
				
				for i in range(30):
					if i < row_string_length:
						wirte_buffer[tag_offset+33+i] = row_string[i]
					else:
						wirte_buffer[tag_offset+33+i] = 32

			if self.album_modified:
				# offset = 63, size=30
				row_string = self.album.encode('utf-8')
				row_string_length = len(row_string)
				
				for i in range(30):
					if i < row_string_length:
						wirte_buffer[tag_offset+63+i] = row_string[i]
					else:
						wirte_buffer[tag_offset+63+i] = 32
						
			if self.comments_modified:
				# offset = 97, size=28 or 30
				max_length = 30
				if self.track_active:
					max_length = 28
				row_string = self.comments.encode('utf-8')
				row_string_length = len(row_string)
				
				for i in range(max_length):
					if i < row_string_length:
						wirte_buffer[tag_offset+97+i] = row_string[i]
					else:
						wirte_buffer[tag_offset+97+i] = 32

			f_handle.write(wirte_buffer)

			f_handle.close()
#アルバムタグが存在するかチェック
def CheckAlbumTag(inTags, inFile, inCheckAlbumFolderNames):
	if len(inCheckAlbumFolderNames) is 0:
		return False
	if inTags is None or inTags.album is None or inTags.album is '':
		fileName = str ( inFile.resolve() )
		for cf in inCheckAlbumFolderNames:
			cf = cf.replace('\\', '\\\\')
			cf = cf.replace (':', '\\:')
			pattern = '^'+cf+"\\\\.+\\\\"
			if re.match(pattern, fileName, re.IGNORECASE ):
			#if cf in fileName:
				logCheckAlbumError.write(fileName+"\n")
				return True
	return False

#アルバムタグ強制セット
def ForceSetAlbumTag(inTags, inFile, inForceSetAlbumConf):
	if len(inForceSetAlbumConf) is 0:
		return False

	fileName = str ( inFile.resolve() )
	for conf in inForceSetAlbumConf:
		cf = conf[0].replace('\\', '\\\\')
		cf = cf.replace (':', '\\:')
		pattern = '^'+cf
		if re.match(pattern, fileName, re.IGNORECASE ):
			inTags.album = conf[1]
			if inTags is None:
				logErrorFile.write(fileName+"\n")
				logErrorFile.write("\tforce set album target but no tags" +"\n")
				return False
			if inTags.track_num is None or inTags.track_num[0] is None or  inTags.track_num[0] is '':
				track = ''
				if re_title_from_albam_filename.match ( inFile.name ):
					track = re_title_from_albam_filename.sub('\\1', inFile.name)
					inTags.track_num = track
				logForceSetAlbumFile.write(fileName+"\n\t"+conf[1]+":"+str(track)+"\n")
			else:
				logForceSetAlbumFile.write(fileName+"\n\t"+conf[1]+"\n")
			return True
	return False

#フォルダ単位で変換処理実行
def ExecTagCheck(outLogPath,inFolder,isCheckOnly,inCheckAlbumFolders, inForceSetAlbumConf):
	print( "checking folder : " + str(inFolder.name) )


	checkAlbumFolderNames = []
	for f in inCheckAlbumFolders:
		checkAlbumFolderNames.append( str(inFolder.resolve()) + "\\" + f)
		
	forceSetAlbumConf = []
	for f in inForceSetAlbumConf:
		forceSetAlbumConf.append( [ str(inFolder.resolve()) + "\\" + f[0], f[1] ])


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
		else:
			#eyed3は、ID3v1からAlbum情報を読み込めていない。V1とV2が異なるケースで、変換できない文字が残ってしまう
			id3v1_tag = MyID3V1(file)
			is_v2tag_copied = id3v1_tag.sjis_to_utf(tags)
			if not isCheckOnly:
				id3v1_tag.save()
				if is_v2tag_copied:
					if ( tags.version == eyed3.id3.ID3_V2_2 or tags.version == eyed3.id3.ID3_V1_0 or tags.version == eyed3.id3.ID3_V1_1):
						tags.save(encoding='utf-16', version=(2,3,0))
					else:
						tags.save(encoding='utf-16', version=tags.version)


		# アルバムタグチェックは、UTFコンバートと関係なく行う

		# ここはチェックだけ
		CheckAlbumTag(tags, file, checkAlbumFolderNames)

		# アルバムタグ強制補正
		res_force_set_album = ForceSetAlbumTag(tags,file,forceSetAlbumConf)
		if not isCheckOnly and res_force_set_album:
			if ( tags.version == eyed3.id3.ID3_V2_2 or tags.version == eyed3.id3.ID3_V1_0 or tags.version == eyed3.id3.ID3_V1_1):
				tags.save(encoding='utf-16', version=(2,3,0))
			else:
				tags.save(encoding='utf-16', version=tags.version)

		#print("***********************")

# Albumチェック対象フォルダ取得
def GetCheckAlbumFolers ( inCheckFile ):
	res = []
	with open(str(inCheckFile.resolve())) as f:
		for s_line in f:
			folder = str(s_line).strip()
			if folder is not '':
				res.append(folder)
	return res

# Album強制セット対象フォルダ取得
def GetForceSetAlbumFolers( inCheckFile ):
	res = []
	with open(str(inCheckFile.resolve())) as f:
		for s_line in f:
			line = str(s_line).strip()
			if line is not '':
				# パス\tアルバム名
				path = re_force_set_album.sub('\\1', line)
				album = re_force_set_album.sub('\\2', line)
				res.append([path,album])
	return res

#main
if __name__ == "__main__":
	scriptPath = Path(__file__).parent

	args = sys.argv
	if len(args) < 2:
		print(	'userge:\n ModifyMusicTagsUTF.py [log out path] [-c] [-ac [conf.txt]] [-fa [conf.txt]] [in convert folder path]\n'
			+ '[-c] check only(not save)\n'
			+ '[-ac] album tag check : config file "root folder path"\n'
			+ '[-fa] force set album tag : config file "target folder path\tAlbumName"')
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
		logConvertFileV1Tag= (outLogPath / "logConvertFileV1Tag.txt").open(mode='w', encoding='UTF-8')
		logConvertFileV1Tag.write("cp932 tag convert modified v1 tag file list\n\n")
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

		isCheckAlbum = False
		checkAlbumFolders = []
		is_ac_conf = False

		isForceSetAlbum = False
		forceSetAlbumConf = []
		is_fa_conf = False

		for count,arg in enumerate(args):
			if count > 1:
				if arg == '-c':
					isCheckOnly = True
				elif arg == '-ac':
					is_ac_conf = True
					isCheckAlbum = True
					logCheckAlbumError = (outLogPath / "logCheckAlbumError.txt").open(mode='w', encoding='UTF-8')
					logCheckAlbumError.write("album check error file list\n\n")
				elif arg == '-fa':
					is_fa_conf = True
					isForceSetAlbum = True
					logForceSetAlbumFile = (outLogPath / "logForceSetAlbumFile.txt").open(mode='w', encoding='UTF-8')
					logForceSetAlbumFile.write("force album tag set file list\n\n")
				else:
					if is_ac_conf :
						checkAlbumFolders = GetCheckAlbumFolers ( Path(arg) )
						is_ac_conf = False
					if is_fa_conf :
						forceSetAlbumConf = GetForceSetAlbumFolers ( Path(arg) )
						is_fa_conf = False
					elif os.path.exists(arg):
						ExecTagCheck(outLogPath,Path(arg),isCheckOnly,checkAlbumFolders, forceSetAlbumConf)

		logConvertFile.close()
		logConvertFileV1StringOver.close()
		logConvertFileV1Tag.close()
		logErrorFile.close()
		logNoTagFile.close()
		logNoTagAlbumFile.close()
		logNoTagUnknownFile.close()
		logSkipFile.close()
		if isCheckAlbum:
			logCheckAlbumError.close()
		if isForceSetAlbum:
			logForceSetAlbumFile.close()
	
