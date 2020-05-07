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

import sys
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

def get_donations(sheet_url):
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
	
def save_donation(db, row, row_hash, published="none"):
	if published == "twitter":
		tweet_status = True
	elif published == "mastodon":
		mast_status = True
		
	db.upsert(
		{
			"hash": row_hash,
			"tweet_status": tweet_status,
			"mast_status": mast_status,
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

def new_donations(db, sheet_url):
	donations = get_donations(sheet_url)
	if donations:
		donation_db = Query()
	
		for row in donations:
			row_hash = make_hash(row)
			if not db.search(donation_db.hash == row_hash):
				save_donation(db, row, row_hash)
				
		return True
			
	else:
		print(f"Fetch {sheet_url} failed.", file=sys.stderr)
		return False
		
def publish_donations(args, db):
	donation_db = Query()
	
	for row in db:
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

def list_donations(db):
	for row in db:
		print_row(row)

def print_row(row):
	print(
		f"Hash: {row['hash']}\n"
		f"Date Seen: {row['dateseen']}\n"
		f"Date: {row['date']}\n"
		f"Amount: {row['amount']}\n"
		f"Category: {row['category']}\n"
		f"Grantee: {row['grantee']}\n"
		f"Link: {row['link']}\n"
		f"Why: {row['why']}\n"
	)

def retrieve_donation(db, hash):
	donation_db = Query()
	row = db.search(donation_db.hash == hash)
	if row:
		print_row(row[0])
	else:
		print(f"Donation {hash} not found.")
		
def delete_donation(db, hash):
	donation_db = Query()
	ids = db.remove(donation_db.hash == hash)
	if ids:
		print(f"Donation {hash} deleted.")
	else:
		print(f"Donation {hash} not found.")

def main():
	parser = argparse.ArgumentParser(description='startsmall charity donation tracker')
	
	parser.add_argument('--maxlen', default=255, type=int, help='Max tweet length')
	parser.add_argument('--db', required=True, help='Database location')
	
	parser.add_argument('--print', default=True, help='Print donations', action='store_true')
	parser.add_argument('--tweet', help='Tweet donations', action='store_true')
	parser.add_argument('--toot', help='Toot donations', action='store_true')
	
	parser_group = parser.add_mutually_exclusive_group(required=True)
	parser_group.add_argument('--new', help='Get & publish new donations', action='store_true')
	parser_group.add_argument('--list', help='List all recorded donations', action='store_true')
	parser_group.add_argument('--delete', help='Delete donation', metavar='HASH', action='store')
	parser_group.add_argument('--retrieve', help='Retrieve & list donation',  metavar='HASH', action='store')
	
	args = parser.parse_args()
	
	db = TinyDB(args.db)
	
	if args.new:
		new_donations(db, sheet_url)
		publish_donations(args, db)
	elif args.list:
		list_donations(db)
	elif args.delete:
		delete_donation(db, args.delete)
	elif args.print:
		retrieve_donation(db, args.retrieve)
	
if __name__ == "__main__":
	main()
