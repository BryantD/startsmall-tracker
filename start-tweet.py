#!/usr/bin/env python3

# Copyright 2020 Bryant Durrell
# # Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
# 
# 1. Redistributions of source code must retain the above copyright
# notice, this list of conditions and the following disclaimer.
# 
# 2. Redistributions in binary form must reproduce the above copyright
# notice, this list of conditions and the following disclaimer in the
# documentation and/or other materials provided with the distribution.
# 
# 3. Neither the name of the copyright holder nor the names of its
# contributors may be used to endorse or promote products derived from
# this software without specific prior written permission.
# 
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS
# IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED
# TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A
# PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED
# TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
# PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
# NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

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

def normalize(row):
	row[0] = row[0].strip()
	row[1] = row[1].replace(" ", "")
	row[2] = row[2].strip()
	row[3] = row[3].strip()
	row[4] = row[4].strip()
	row[5] = row[5].strip()
	
	return row

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
			trimmed_donations.append(normalize(row))
			
	return trimmed_donations
	
def make_hash(row):	
	m = hashlib.md5()
	m.update(str.encode(row[0] + row[1] + row[3]))
	return m.hexdigest()
	
def save_donation(db, row, row_hash):
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

def make_text(row, max_length):
	if (row[0] == ""):
		row[0] = "None"
	
	text = f"Date: {row[0]}\nAmount: {row[1]}\nCategory: {row[2]}\nGrantee: {row[3]}\nLink: {row[4]}\n\n"
	text += f"Source: {data_source}"

	if len(text) > max_length:
		text = f"Date: {row[0]}\nAmount: {row[1]}\nGrantee: {row[3]}"
		
	if len(text) > max_length:
		text = f"Amount: {row[1]}\nGrantee: {row[3]}"
	
	return text

def main():
	parser = argparse.ArgumentParser(description='startsmall charity donation tracker')
	
	parser.add_argument('--maxlen', default=255, type=int, help='Max tweet length')
	parser.add_argument('--db', required=True, help='Database location')
	
	parser.add_argument('--print', default=True, help='Print donations', action='store_true')
	parser.add_argument('--tweet', help='Tweet donations', action='store_true')
	parser.add_argument('--toot', help='Toot donations', action='store_true')
	
	parser.add_argument('--new', default=True, help='Get new donations (default)', action='store_true')
	parser.add_argument('--list', help='Show all recorded donations', action='store_true')
	parser.add_argument('--delete', help='Hash of a donation to delete', action='store')
	parser.add_argument('--retrieve', help='Hash of a donation to retrieve', action='store')
	
	args = parser.parse_args()
	
	db = TinyDB(args.db)
	
	donations = get_donations()
	donation_db = Query()
	
	for row in donations:
		row_hash = make_hash(row)
		if not db.search(donation_db.hash == row_hash):
			save_donation(db, row, row_hash)
			
			text = make_text(row, args.maxlen)
			
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
