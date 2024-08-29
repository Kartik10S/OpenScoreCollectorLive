import os, sys
from os import listdir
from os.path import isfile, join
from urllib.parse import urlparse
import hashlib
import requests
import logging
from datetime import datetime, timedelta, timezone
import datetime
from time import strftime, strptime
import time
from zipfile import ZipFile
import shutil
import json
from threading import Thread
import traceback
from config import *

outdatafolder = "../data/"
datadomain = "xxx"
leaguepupular = ["euro-2024", "copa-america", "england", "champions-league", "spain", "italy", "germany", "france", "holland", "europa-league", "europa-conference-league", "portugal", "uefa-nations-league"]
matches_updated = []

livescoretoken = "LbC2S31VjzszcKPHb0uaY"
if os.path.isfile("livescoretoken.conf"):
	with open("livescoretoken.conf", "r") as file:
		livescoretoken = file.read()

env_loglevel = os.environ.get('LOG_LEVEL', "INFO")
if env_loglevel == "ERROR":
	loglevel = logging.ERROR
elif env_loglevel == "DEBUG":
	loglevel = logging.DEBUG
else:
	loglevel = logging.INFO

env_logfile = os.environ.get('LOG_FILE', False)
if env_logfile:
	loghandler = [ logging.FileHandler("debug.log"), logging.StreamHandler()]
else:
	loghandler = [ logging.StreamHandler()]

logging.basicConfig(
    level=loglevel,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=loghandler
)

def sendnotify(message):
	# check in cache
	cachefilename = "%s.cache" % datetime.date.today().strftime("%Y%m%d")
	hasher = hashlib.md5()
	hasher.update(message.encode('utf-8'))
	texthash = hasher.hexdigest()

	if os.path.isfile(cachefilename):
		with open(cachefilename, "r+") as file:
			lstcache = []
			for line in file.readlines():
				lstcache.append(line.strip())
			if texthash in lstcache:
				return
			else:
				file.write("%s\n" % texthash)
	else:
		with open(cachefilename, "w") as file:
			file.write("%s\n" % texthash)

	# send
	send_text = f'https://api.telegram.org/bot{telegram_bot_token}/sendMessage?chat_id={telegram_chatid}&parse_mode=Markdown&text={message}'
	response = requests.get(send_text)
	return response.json()

def savedata(content, path):
	try:
		with open(path, 'w', encoding='utf-8') as f:
			f.write(content)
	except Exception as e:
		logging.error(f"Error in savedata: {e}")
	logging.info("saved data to %s" % path)

def scheduleLiveScore(dateget, updatedetail = False, extenddate = False, whitelist = None):
	url = "https://prod-public-api.livescore.com/v1/api/app/date/soccer/%s/0"%(dateget.strftime("%Y%m%d"))
	res = requests.get(url)
	res.encoding = 'utf-8'
	bodyres = res.json()
	lstleague = []
	leagueindex = {}
	firstleague = None
	
	for leagueid, league in enumerate(bodyres['Stages']):
		if leagueid > 10:
			break
		league['img'] = "https://static.livescore.com/i2/fh/%s.jpg" % (league['Ccd']) if ("Ccd" in league.keys() and "friendlies" not in league['Ccd'] and "the-games-men" not in league['Ccd'] and "conference-league" not in league['Ccd']) else "%s/images/cup.png" % (datadomain)
		matchfound = 0
		if len(league["Events"]) == 0:
			continue
		for match in league['Events']:
			match['T1img'] = "https://lsm-static-prod.livescore.com/medium/%s" % (match['T1'][0]['Img']) if "Img" in match['T1'][0].keys() else "%s/images/cup.png" % (datadomain)
			match['T2img'] = "https://lsm-static-prod.livescore.com/medium/%s" % (match['T2'][0]['Img']) if "Img" in match['T2'][0].keys() else "%s/images/cup.png" % (datadomain)
			if updatedetail:
				resum = summaryLiveScore(match['Eid'], rate=1)
				if resum['ispopular']:
					matchfound += 1
			else:
				matchfound += 1
		if firstleague == None:
			firstleague = league
		if (matchfound / len(league["Events"])) > 0.5 or (league['Ccd'] in leaguepupular):
			leagueindex[league['Sid']] = len(lstleague)
			lstleague.append(league)
	
	if len(lstleague) == 0:
		lstleague.append(firstleague)
	savedata(json.dumps({'Stages': lstleague}, ensure_ascii=False), "%s/schedules/%s.json" % (outdatafolder, dateget.strftime("%Y%m%d")))

def updateSchedulefull():
	today = datetime.date.today()
	scheduleLiveScore(today, True, True)
	# before 3 days and after 3 days
	for i in range(3):
		scheduleLiveScore((today + datetime.timedelta(days=(-1)*(i+1))), True)
		scheduleLiveScore((today + datetime.timedelta(days=(i+1))), True)

def updatelive(datestr, rate=0):
	jsonpath = "%s/schedules/%s.json" % (outdatafolder, datestr)
	if not os.path.isfile(jsonpath):
		logging.error("Update full before: %s" % datestr)
		sendnotify("Error in update today: update full before (%s)" % datestr)
		exit()
	else:
		with open(jsonpath, encoding="utf8") as f:
			liveschedule = json.load(f)
		ischange = False
		for league in liveschedule['Stages']:
			for match in league['Events']:
				if match['Eid'] in matches_updated: continue
				matches_updated.append(match['Eid'])
				if match['Eps'] not in ['FT', 'AP', 'AET']:
					resum = summaryLiveScore(match['Eid'], rate=rate)
					rematch = resum['match']
					match['Eps'] = rematch['Eps']
					if 'Tr1' in rematch.keys():
						match['Tr1'] = rematch['Tr1']
						match['Tr2'] = rematch['Tr2']
					if 'Trh1' in rematch.keys():
						match['Trh1'] = rematch['Trh1']
						match['Trh2'] = rematch['Trh2']
					if 'Tr1OR' in rematch.keys():
						match['Tr1OR'] = rematch['Tr1OR']
						match['Tr2OR'] = rematch['Tr2OR']
					ischange = True
		if ischange:
			savedata(json.dumps(liveschedule, ensure_ascii=False), "%s/schedules/%s.json" % (outdatafolder, datestr))

def updateToday(rate=0):
	logging.info("Update today rate %d start" % rate)
	today = datetime.date.today()
	# load current
	# today
	updatelive(today.strftime("%Y%m%d"), rate=rate)
	updatelive((today + datetime.timedelta(days=(-1))).strftime("%Y%m%d"), rate=rate)
	logging.info("Update today rate %d done" % rate)

def summaryLiveScore(matchid, rate=0):
	url = "https://prod-public-api.livescore.com/v1/api/app/scoreboard/soccer/%s"%(matchid)
	res = requests.get(url)
	match = None
	if res.status_code != 200:
		logging.error("Error in summaryLiveScore %s, status not 200, %d" % (url, res.status_code))
	else:
		res.encoding = 'utf-8'
		match = res.json()
		match['T1img'] = "https://lsm-static-prod.livescore.com/medium/%s" % (match['T1'][0]['Img']) if "Img" in match['T1'][0].keys() else "%s/images/cup.png" % (datadomain)
		match['T2img'] = "https://lsm-static-prod.livescore.com/medium/%s" % (match['T2'][0]['Img']) if "Img" in match['T2'][0].keys() else "%s/images/cup.png" % (datadomain)
	
def printUsage():
	print("Usage %s <action> [option]" % sys.argv[0])

if __name__ == "__main__":
	if len(sys.argv) < 2:
		printUsage()
		exit(0)

	try:
		if sys.argv[1] == "updatefull":
			updateSchedulefull()
		elif sys.argv[1] == "updatetoday": # norate for scoring
			updateToday()
		else:
			printUsage()
			exit(0)
	except Exception as e:
		traceback_str = traceback.format_exc()
		sendnotify("Unexpected Error in %s: %s" % (sys.argv[1], traceback_str))