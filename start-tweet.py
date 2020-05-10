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
from time import sleep
from credentials import *
from config import *


def download_donations(db, sheet_url):
    r = requests.get(sheet_url)
    if r.ok:
        decoded_content = r.content.decode("utf-8")
        cr = csv.reader(decoded_content.splitlines(), delimiter=",")

        distributed_flag = date_flag = False

        raw_donations = list(cr)
        trimmed_donations = []
        for row in raw_donations:
            # Skip past initial rows
            if row[0] == "Distributed:":
                distributed_flag = True
            elif (row[0] == "Date") and distributed_flag:
                date_flag = True
            elif date_flag:

                donation = {
                    "date": row[0].strip(),
                    "amount": row[1].replace(" ", ""),
                    "category": row[2].strip(),
                    "grantee": row[3].strip(),
                    "link": row[4].strip(),
                    "why": row[5].strip(),
                }

                save_donation(db, donation)

        return True

    else:
        print(f"Fetch {sheet_url} failed.", file=sys.stderr)
        return False


def save_donation(db, donation, published="none"):
    db_query = Query()
    m = hashlib.md5()

    m.update(str.encode(donation["date"] + donation["amount"] + donation["grantee"]))
    donation["hash"] = m.hexdigest()

    if not db.search((db_query.hash == donation["hash"])):
        donation["date_seen"] = date.today().strftime("%Y-%m-%d")
        donation["tweet_status"] = False
        donation["mast_status"] = False

    if published == "twitter":
        donation["tweet_status"] = True
    elif published == "mastodon":
        donation["mast_status"] = True

    db.upsert(donation, db_query.hash == donation["hash"])


def make_text(row, max_length):
    if row["date"] == "":
        row["date"] = "None"

    text = f"Date: {row['date']}\nAmount: {row['amount']}\nCategory: {row['category']}\nGrantee: {row['grantee']}\nLink: {row['link']}"

    if len(text) > max_length:
        text = (
            f"Date: {row['date']}\nAmount: {row['amount']}\nGrantee: {row['grantee']}"
        )

    if len(text) > max_length:
        text = f"Amount: {row['amount']}\nGrantee: {row['grantee']}"

    return text


def publish_donations(db, args):
    db_query = Query()

    if args.print:
        for donation in db:
            text = make_text(donation, args.maxlen)
            print(text)
            print("\n")
    if args.toot:
        for donation in db.search(db_query.mast_status == False):
            text = make_text(donation, args.maxlen)
            if args.test:
                print(text)
            else:
                mastodon = Mastodon(
                    access_token=mastodon_access_token,
                    api_base_url="https://botsin.space",
                )
                mastodon.toot(text)
                save_donation(db, donation, published="mastodon")
            sleep(args.sleep * 60)
    if args.tweet:
        for donation in db.search(db_query.tweet_status == False):
            text = make_text(donation, args.maxlen)
            if args.test:
                print(text)
            else:
                auth = tweepy.OAuthHandler(
                    twitter_consumer_key, twitter_consumer_secret
                )
                auth.set_access_token(twitter_access_token, twitter_access_token_secret)
                api = tweepy.API(auth)
                try:
                    api.update_status(text)
                    save_donation(db, donation, published="twitter")
                except tweepy.TweepError as e:
                    print(f"Tweet failed: {e.response.text}", file=sys.stderr)
            sleep(args.sleep * 60)


def list_donations(db):
    for row in db:
        print_row(row)


def print_row(row):
    print(
        f"Hash: {row['hash']}\n"
        f"Date Seen: {row['date_seen']}\n"
        f"Date: {row['date']}\n"
        f"Amount: {row['amount']}\n"
        f"Category: {row['category']}\n"
        f"Grantee: {row['grantee']}\n"
        f"Link: {row['link']}\n"
        f"Why: {row['why']}\n"
        f"Tweet Status: {row['tweet_status']}\n"
        f"Mastodon Status: {row['mast_status']}\n"
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
    parser = argparse.ArgumentParser(description="startsmall charity donation tracker")

    parser.add_argument("--maxlen", default=255, type=int, help="Max tweet length")
    parser.add_argument("--db", required=True, help="Database location")
    parser.add_argument("--test", help="Test mode", action="store_true")

    parser.add_argument("--print", help="Print donations", action="store_true")
    parser.add_argument("--tweet", help="Tweet donations", action="store_true")
    parser.add_argument("--toot", help="Toot donations", action="store_true")

    parser.add_argument(
        "--sleep",
        help="Minutes between publishing donations",
        default=0,
        type=int,
        action="store",
    )

    parser_group = parser.add_mutually_exclusive_group(required=True)
    parser_group.add_argument(
        "--download", help="Download new donations", action="store_true"
    )
    parser_group.add_argument(
        "--publish", help="Publish unpublished donations", action="store_true"
    )
    parser_group.add_argument(
        "--list", help="List all recorded donations", action="store_true"
    )
    parser_group.add_argument(
        "--delete", help="Delete donation", metavar="HASH", action="store"
    )
    parser_group.add_argument(
        "--retrieve", help="Retrieve & list donation", metavar="HASH", action="store"
    )

    args = parser.parse_args()

    db = TinyDB(args.db)

    if args.download:
        download_donations(db, sheet_url)
    elif args.publish:
        publish_donations(db, args)
    elif args.list:
        list_donations(db)
    elif args.delete:
        delete_donation(db, args.delete)
    elif args.print:
        retrieve_donation(db, args.retrieve)


if __name__ == "__main__":
    main()
