# -*- coding: utf-8 -*-
# !/usr/bin/python3

# python3 -m pip install yagmail tweepy html5lib pdf2image pylovepdf psutil --no-cache-dir
# sudo apt install poppler-utils -y
import datetime
import json
import os
import shutil
import psutil
import requests
import tweepy
import yagmail
import pdf2image
import traceback
import logging

from bs4 import BeautifulSoup
from pylovepdf.tools.officepdf import OfficeToPdf


def get911(key):
    with open('/home/pi/.911') as f:
        data = json.load(f)
    return data[key]


def getLog():
    try:
        with open(CONFIG_FILE) as inFile:
            log = json.load(inFile)
    except Exception:
        log = {}

    return log


def getPosts():
    # Get last tweeted post date and title
    log = getLog()

    # Make soup
    url = "https://wseries.com/notice-boards/?category=" + str(datetime.datetime.now().year)
    r = requests.get(url, timeout=30).text
    soup = BeautifulSoup(r, 'html5lib')

    # Get Last Race
    lastRace = soup.find("a", {"class": "archive__item__title"})
    lastRaceTitle = lastRace.text.split(" | ")[1].strip().title()

    # Get Race Documents
    newPosts = []
    url = lastRace.get("href")
    logger.info(url)
    r = requests.get(url).text
    soup = BeautifulSoup(r, 'html5lib')
    documents = soup.find("div", {"class": "files__table"}).find_all("a")
    for document in reversed(documents):
        # Get title and href
        postTitle = document.find("h4").text.strip()
        postHref = document.get("href")

        # Check if post is valid ? Add to new posts : break
        if {"title": postTitle, "href": postHref} not in log:
            newPosts.append({"title": postTitle, "href": postHref})

    return lastRaceTitle, newPosts


def getScreenshots(postHref):
    try:
        # Reset tmpFolder
        if os.path.exists(tmpFolder):
            shutil.rmtree(tmpFolder)
        os.mkdir(tmpFolder)

        # Check if postHref is already an image
        fileExt = postHref.split(".")[-1]
        if fileExt in ["png", "jpg", "jpeg"]:
            tmpFile = os.path.join(tmpFolder, "tmp." + fileExt)
            with open(tmpFile, 'wb') as imgFile:
                imgFile.write(requests.get(postHref).content)
            hasPics = True
        else:
            # Download PDF
            postFile = os.path.join(tmpFolder, "tmp." + fileExt)
            with open(postFile, "wb") as inFile:
                inFile.write(requests.get(postHref).content)

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
        logger.error("Failed to screenshot")
        hasPics = False

    return hasPics


def getRaceHashtags(eventTitle):
    hashtags = ""

    try:
        with open(HASHTAGS_FILE) as inFile:
            hashtags = json.load(inFile)[eventTitle]
    except Exception as ex:
        logger.error("Failed to get Race hashtags")
        yagmail.SMTP(EMAIL_USER, EMAIL_APPPW).send(EMAIL_RECEIVER, "Failed to get Race hashtags - " + os.path.basename(__file__), str(ex) + "\n\n" + eventTitle)

    return hashtags


def tweet(tweetStr, hasPics):
    try:
        media_ids = []
        if hasPics:
            imageFiles = sorted([file for file in os.listdir(tmpFolder) if file.split(".")[-1] in ["png", "jpg", "jpeg"]])
            media_ids = [api.media_upload(os.path.join(tmpFolder, image)).media_id_string for image in imageFiles]

        api.update_status(status=tweetStr, media_ids=media_ids)
        logger.info("Tweeted")
    except Exception as ex:
        logger.error("Failed to Tweet")
        yagmail.SMTP(EMAIL_USER, EMAIL_APPPW).send(EMAIL_RECEIVER, "Failed to Tweet - " + os.path.basename(__file__), str(ex) + "\n\n" + tweetStr)


def batchDelete():
    logger.info("Deleting all tweets from the account @" + api.verify_credentials().screen_name)
    for status in tweepy.Cursor(api.user_timeline).items():
        try:
            api.destroy_status(status.id)
        except Exception:
            pass


def main():
    # Get latest posts
    eventTitle, newPosts = getPosts()
    if eventTitle is None:
        return

    # Set hashtags
    hashtags = getRaceHashtags(eventTitle)
    hashtags += " " + "#WSeries #GrandPrix"

    # Go through each new post
    for post in newPosts:
        # Get post info
        postTitle, postHref = post["title"], post["href"]
        logger.info(postTitle)
        logger.info(postHref)

        # Screenshot DPF
        hasPics = getScreenshots(postHref)

        # Set date
        postDate = datetime.datetime.strftime(datetime.datetime.utcnow(), "%Y/%m/%d %H:%M UTC")

        # Tweet!
        tweet(postTitle + "\n\n" + "Published at: " + postDate + "\n\n" + postHref + "\n\n" + hashtags, hasPics)

        # Save log
        with open(CONFIG_FILE) as inFile:
            data = list(reversed(json.load(inFile)))
            data.append(post)
        with open(CONFIG_FILE, "w") as outFile:
            json.dump(list(reversed(data)), outFile, indent=2)


if __name__ == "__main__":
    # Set Logging
    LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.path.abspath(__file__).replace(".py", ".log"))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()])
    logger = logging.getLogger()

    logger.info("----------------------------------------------------")
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

    # Set temp folder
    tmpFolder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tmp")
    CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    HASHTAGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raceHashtags.json")

    # Check if script is already running
    procs = [proc for proc in psutil.process_iter(attrs=["cmdline"]) if os.path.basename(__file__) in '\t'.join(proc.info["cmdline"])]
    if len(procs) > 2:
        logger.info("isRunning")
    else:
        try:
            main()
        except Exception as ex:
            logger.error(traceback.format_exc())
            yagmail.SMTP(EMAIL_USER, EMAIL_APPPW).send(EMAIL_RECEIVER, "Error - " + os.path.basename(__file__), str(traceback.format_exc()))
        finally:
            logger.info("End")
