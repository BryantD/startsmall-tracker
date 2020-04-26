#!/usr/bin/env python3

import argparse
import requests
import csv
import hashlib
import tweepy
from mastodon import Mastodon
from tinydb import TinyDB, Query
from datetime import date
from credentials import *
from config import *

def get_donations():
	r = requests.get(sheet_url)
	decoded_content = r.content.decode("utf-8")
	cr = csv.reader(decoded_content.splitlines(), delimiter=",")

	distributed_flag = date_flag = False

	raw_donations = list(cr)
	trimmed_donations = []
	for row in raw_donations:
		if row[0] == "Distributed:":
			distributed_flag = True
		elif (row[0] == "Date") and distributed_flag:
			date_flag = True
		elif date_flag:
			trimmed_donations.append(row)
			
	return trimmed_donations
	
def make_hash(row):	
	m = hashlib.md5()
	m.update(str.encode(row[0] + row[1] + row[3]))
	return m.hexdigest()
	
def save_donation(db, row, row_hash):
	print(row)
	db.insert(
		{
			"hash": row_hash,
			"dateseen": date.today().strftime("%Y-%m-%d"),
			"date": row[0],
			"amount": row[1],
			"category": row[2],
			"grantee": row[3],
			"link": row[4],
			"why": row[5]
		}
	)

def make_text(row):
	if (row[0] == ""):
		row[0] = "None"
	
	text = f"Date: {row[0]}\nAmount: {row[1]}\nCategory: {row[2]}\nGrantee: {row[3]}\nLink: {row[4]}\n\n"
	text += f"Source: {data_source}"
	return text

def main():
	parser = argparse.ArgumentParser(description='startsmall charity donation tracker')
	parser.add_argument('--maxlen', default=255, type=int, help='Max tweet length')
	parser.add_argument('--db', required=True, help='Database location')
	parser.add_argument('--print', help='Print mixtape', action='store_true')
	parser.add_argument('--tweet', help='Tweet mixtape', action='store_true')
	parser.add_argument('--toot', help='Toot mixtape', action='store_true')
	args = parser.parse_args()
	
	db = TinyDB(args.db)
	
	donations = get_donations()
	donation_db = Query()
	
	for row in donations:
		row_hash = make_hash(row)
		if not db.search(donation_db.hash == row_hash):
			save_donation(db, row, row_hash)
			
			text = make_text(row)
			
			if args.print:
				print(text)
			if args.toot:
				mastodon = Mastodon(
					access_token=mastodon_access_token,
					api_base_url = 'https://botsin.space')
				mastodon.toot(text)
			if args.tweet:
				auth = tweepy.OAuthHandler(twitter_consumer_key, twitter_consumer_secret)
				auth.set_access_token(twitter_access_token, twitter_access_token_secret)
				api = tweepy.API(auth)
				api.update_status(text)

if __name__ == "__main__":
	main()
