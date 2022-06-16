# -*- coding: utf-8 -*-
# !/usr/bin/python3

# python3 -m pip install yagmail tweepy html5lib pdf2image pylovepdf --no-cache-dir
# sudo apt install poppler-utils -y
import datetime
import json
import os
import shutil

import requests
import tweepy
import yagmail
import pdf2image
from bs4 import BeautifulSoup
from pylovepdf.tools.officepdf import OfficeToPdf


def get911(key):
    with open('/home/pi/.911') as f:
        data = json.load(f)
    return data[key]


CONSUMER_KEY = get911('TWITTER_WSERIES_CONSUMER_KEY')
CONSUMER_SECRET = get911('TWITTER_WSERIES_CONSUMER_SECRET')
ACCESS_TOKEN = get911('TWITTER_WSERIES_ACCESS_TOKEN')
ACCESS_TOKEN_SECRET = get911('TWITTER_WSERIES_ACCESS_TOKEN_SECRET')
EMAIL_USER = get911('EMAIL_USER')
EMAIL_APPPW = get911('EMAIL_APPPW')
EMAIL_RECEIVER = get911('EMAIL_RECEIVER')
ILOVEPDF_API_KEY_PUBLIC = get911('ILOVEPDF_API_KEY_PUBLIC')

auth = tweepy.OAuthHandler(CONSUMER_KEY, CONSUMER_SECRET)
auth.set_access_token(ACCESS_TOKEN, ACCESS_TOKEN_SECRET)
api = tweepy.API(auth)


def getLog():
    try:
        with open(LOG_FILE) as inFile:
            log = json.load(inFile)
    except Exception:
        log = {}

    return log


def getPosts():
    # Get last tweeted post date and title
    log = getLog()

    # Make soup
    url = "https://wseries.com/notice-boards/?category=" + str(datetime.datetime.now().year)
    soup = BeautifulSoup(requests.get(url).text, 'html5lib')

    # Get Last Race
    lastRace = soup.find("a", {"class": "archive__item__title"})
    lastRaceTitle = lastRace.text.split(" | ")[1].strip().title()
    print("lastRaceTitle - " + lastRaceTitle)

    # Get Race Documents
    newPosts = []
    soup = BeautifulSoup(requests.get(lastRace.get("href")).text, 'html5lib')
    documents = soup.find("div", {"class": "board__table"}).find_all("a")
    for document in reversed(documents):
        # Get title and href
        postTitle = document.find("span").text.strip()
        postHref = document.get("href")

        # Check if post is valid ? Add to new posts : break
        if {"title": postTitle, "href": postHref} not in log:
            newPosts.append({"title": postTitle, "href": postHref})

    return lastRaceTitle, newPosts


def getScreenshots(pdfHref):
    try:
        # Reset tmpFolder
        if os.path.exists(tmpFolder):
            shutil.rmtree(tmpFolder)
        os.mkdir(tmpFolder)

        # Download PDF
        postFile = os.path.join(tmpFolder, "tmp." + pdfHref.split(".")[-1])
        with open(postFile, "wb") as inFile:
            inFile.write(requests.get(pdfHref).content)

        # Convert docx to pdf
        if postFile[-5:] == ".docx" or postFile[-4:] == ".doc":
            t = OfficeToPdf(ILOVEPDF_API_KEY_PUBLIC, verify_ssl=True, proxies=[])
            t.add_file(os.path.join(os.path.dirname(os.path.abspath(__file__)), postFile))
            t.set_output_folder(tmpFolder)
            t.execute()
            t.download()
            t.delete_current_task()
            postFile = sorted([file for file in os.listdir(tmpFolder) if file.split(".")[-1] == "pdf"])[0]
            postFile = os.path.join(tmpFolder, postFile)

        # Check what OS
        if os.name == "nt":
            poppler_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "poppler-win\Library\bin")
            pages = pdf2image.convert_from_path(poppler_path=poppler_path, pdf_path=postFile)
        else:
            pages = pdf2image.convert_from_path(pdf_path=postFile)

        # Save the first four pages
        for idx, page in enumerate(pages[0:4]):
            jpgFile = os.path.join(tmpFolder, "tmp_" + str(idx) + ".jpg")
            page.save(jpgFile)
        hasPics = True
    except Exception as ex:
        print("Failed to screenshot")
        print(ex)
        hasPics = False

    return hasPics


def getRaceHashtags(eventTitle):
    hashtags = ""

    try:
        with open(HASHTAGS_FILE) as inFile:
            hashtags = json.load(inFile)[eventTitle]
    except Exception as ex:
        print("Failed to get Race hashtags")
        yagmail.SMTP(EMAIL_USER, EMAIL_APPPW).send(EMAIL_RECEIVER, "Failed to get Race hashtags - " + os.path.basename(__file__), str(ex) + "\n\n" + eventTitle)

    return hashtags


def tweet(tweetStr, hasPics):
    try:
        media_ids = []
        if hasPics:
            imageFiles = sorted([file for file in os.listdir(tmpFolder) if file.split(".")[-1] == "jpg"])
            media_ids = [api.media_upload(os.path.join(tmpFolder, image)).media_id_string for image in imageFiles]

        api.update_status(status=tweetStr, media_ids=media_ids)
        print("Tweeted")
    except Exception as ex:
        print("Failed to Tweet")
        yagmail.SMTP(EMAIL_USER, EMAIL_APPPW).send(EMAIL_RECEIVER, "Failed to Tweet - " + os.path.basename(__file__), str(ex) + "\n\n" + tweetStr)


def batchDelete():
    print("Deleting all tweets from the account @" + api.verify_credentials().screen_name)
    for status in tweepy.Cursor(api.user_timeline).items():
        try:
            api.destroy_status(status.id)
        except Exception:
            pass


def main():
    # Get latest posts
    eventTitle, newPosts = getPosts()
    newPosts = list(reversed(newPosts))

    # Set hashtags
    hashtags = getRaceHashtags(eventTitle)
    hashtags += " " + "#WSeries #Formula #GrandPrix"

    # Go through each new post
    for post in newPosts:
        # Get post info
        postTitle, postHref = post["title"], post["href"]
        print(postTitle)
        print(postHref)

        # Screenshot DPF
        hasPics = getScreenshots(postHref)

        # Set date
        postDate = datetime.datetime.strftime(datetime.datetime.utcnow(), "%Y/%m/%d %H:%M UTC")

        # Tweet!
        tweet("NEW DOC" + "\n\n" + postTitle + "\n\n" + "Published at: " + postDate + "\n\n" + postHref + "\n\n" + hashtags, hasPics)

        # Save log
        with open(LOG_FILE) as inFile:
            data = list(reversed(json.load(inFile)))
            data.append(post)
        with open(LOG_FILE, "w") as outFile:
            json.dump(list(reversed(data)), outFile, indent=2)


if __name__ == "__main__":
    print("----------------------------------------------------")
    print(str(datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")))

    # Set temp folder
    tmpFolder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tmp")
    LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "log.json")
    HASHTAGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raceHashtags.json")
    ISRUNNING_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "isRunning.tmp")

    # Check if isRunning file exists
    if os.path.exists(ISRUNNING_FILE):
        print("isRunning")
    else:
        # Create isRunning file
        open(ISRUNNING_FILE, "x")

        try:
            main()
        except Exception as ex:
            print(ex)
            yagmail.SMTP(EMAIL_USER, EMAIL_APPPW).send(EMAIL_RECEIVER, "Error - " + os.path.basename(__file__), str(ex))
        finally:
            # Remove isRunning file
            os.remove(ISRUNNING_FILE)
            print("End")
