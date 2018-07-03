# standard Python library imports
import codecs
import csv
import logging
import os
import sys
import time

# handle different python versions
try:
    from http.client import HTTPException
    from urllib.request import urlopen
    from urllib.error import HTTPError, URLError
    VERSION = 3
except ImportError:
    from httplib import HTTPException
    from urllib2 import urlopen, HTTPError, URLError
    VERSION = 2

# extra required packages
from bs4 import BeautifulSoup

try:
    import lxml
    PARSER = "lxml"
except ImportError:
    PARSER = "html.parser"

# Tumblr specific constants
TUMBLR_URL = "/api/read"

# configuration variables
ENCODING = "utf-8"

# most filesystems have a limit of 255 bytes per name but we also need room for a '.html' extension
NAME_MAX_BYTES = 250


def unescape(s):
    """ replace Tumblr's escaped characters with ones that make sense for saving in an HTML file """

    if s is None:
        return ""

    # html entities
    s = s.replace("&#13;", "\r")

    # standard html
    s = s.replace("&lt;", "<")
    s = s.replace("&gt;", ">")
    s = s.replace("&amp;", "&") # this has to be last

    return s


# based on http://stackoverflow.com/a/13738452
def utf8_lead_byte(b):
    """ a utf-8 intermediate byte starts with the bits 10xxxxxx """
    return (ord(b) & 0xC0) != 0x80


def byte_truncate(text):
    """ if text[max_bytes] is not a lead byte, back up until one is found and truncate before that character """
    s = text.encode(ENCODING)
    if len(s) <= NAME_MAX_BYTES:
        return s

    if ENCODING == "utf-8":
        lead_byte = utf8_lead_byte
    else:
        raise NotImplementedError()

    i = NAME_MAX_BYTES
    while i > 0 and not lead_byte(s[i]):
        i -= 1

    return s[:i]


def savePost(post, save_folder, header="", use_csv=False, save_file=None):
    """ saves an individual post and any resources for it locally """

    if use_csv:
        assert save_file, "Must specify a file to save CSV data to."

    slug = post["url-with-slug"].rpartition("/")[2]
    date_gmt = post["date-gmt"]

    if use_csv:
        # only append here to preserve other posts
        mode = "a"
        if VERSION == 2:
            # must be opened in binary mode to avoid line break bugs on Windows
            mode += "b"
        #f = open(save_file, mode)
        #writer = csv.writer(f)
        #row = [slug, date_gmt]
    else:
        slug = byte_truncate(slug)
        if VERSION == 3:
            slug = slug.decode(ENCODING)
        file_name = os.path.join(save_folder, slug + ".html")

    postType = post["type"]
    #print(postType)

    if post["type"] == "regular":
        title = ""
        title_tag = post.find("regular-title")
        if title_tag:
            title = unescape(title_tag.string)
        body = ""
        body_tag = post.find("regular-body")
        if body_tag:
            body = unescape(body_tag.string)

    if post["type"] == "photo":
        caption = ""
        caption_tag = post.find("photo-caption")
        if caption_tag:
            caption = unescape(caption_tag.string)
        image_url = post.find("photo-url", {"max-width": "1280"}).string

        image_filename = image_url.rpartition("/")[2]
        if VERSION == 2:
            image_filename = image_filename.encode(ENCODING)
        image_folder = os.path.join(save_folder, "images")
        if not os.path.exists(image_folder):
            os.mkdir(image_folder)
        local_image_path = os.path.join(image_folder, image_filename)

        if not os.path.exists(local_image_path):
            # only download images if they don't already exist
            print("Downloading a photo. This may take a moment.")
            try:
                image_response = urlopen(image_url)
                image_file = open(local_image_path, "wb")
                image_file.write(image_response.read())
                image_file.close()
            except HTTPError as e:
                logging.warning('HTTPError = ' + str(e.code))
            except URLError as e:
                logging.warning('URLError = ' + str(e.reason))
            except HTTPException as e:
                logging.warning('HTTPException')
            except Exception:
                import traceback
                logging.warning('generic exception: ' + traceback.format_exc())

    if post["type"] == "video":
        #print('video found')
        vid_player = post.find('video-player')
        #vid_src = vid_player.find('source')
        vid_player = str(vid_player).replace('&lt;','<').replace('&gt;','>')
        vid_player = BeautifulSoup(vid_player, PARSER)
        vid_src = vid_player.find('source')
        vid_src_url = vid_src['src']
        vid_src_fileName = str(vid_src_url).split('/')[-2:]
        #print(len(str(vid_src_fileName[1])))
        if len(str(vid_src_fileName[1])) < 5:
            vid_src_fileName = str(vid_src_fileName[0])
        else:
            vid_src_fileName = str(vid_src_fileName[1])                    
        
        vid_src_fileName = vid_src_fileName + '.' + str(vid_src['type']).split("/")[1]
        #print(vid_src_url)
        #print(vid_src_fileName)
        video_folder = os.path.join(save_folder, "videos")
        if not os.path.exists(video_folder):
            os.mkdir(video_folder)
        local_video_path = os.path.join(video_folder, vid_src_fileName)    
        #print(local_video_path)
        if not os.path.exists(local_video_path):
            # only download videos if they don't already exist
            print("Downloading a video. This may take a moment.")
            try:
                image_response = urlopen(vid_src_url)
                image_file = open(local_video_path, "wb")
                image_file.write(image_response.read())
                image_file.close()
            except HTTPError as e:
                print(vid_src_url)
                logging.warning('HTTPError = ' + str(e.code))
            except URLError as e:
                logging.warning('URLError = ' + str(e.reason))
            except HTTPException as e:
                logging.warning('HTTPException')
            except Exception:
                import traceback
                logging.warning('generic exception: ' + traceback.format_exc())

def backup(account, use_csv=False, save_folder=None, start_post = 0):
    """ make an HTML file for each post or a single CSV file for all posts on a public Tumblr blog account """

    if use_csv:
        print("CSV mode activated.")
        print("Data will be saved to " + account + "/" + account + ".csv")

    print("Getting basic information.")

    # make sure there's a folder to save in
    if not os.path.exists(save_folder):
        os.mkdir(save_folder)

    # start by calling the API with just a single post
    url = "http://" + account + TUMBLR_URL + "?num=1"
    response = urlopen(url)
    soup = BeautifulSoup(response.read(), PARSER)

    # if it's a backup to CSV then make sure that we have a file to use
    if use_csv:
        save_file = os.path.join(save_folder, account + ".csv")
        # add the header row
        f = open(save_file, "w") # erases any existing data
        f.write("Slug,Date (GMT),Regular Title,Regular Body,Photo Caption,Photo URL,Quote Text,Quote Source,Link Text,Link URL,Link Description,Tags\r\n") # 12 columns
        f.close()
    else:
        # collect all the meta information
        tumblelog = soup.find("tumblelog")
        title = tumblelog["title"]
        description = tumblelog.string

        # use it to create a generic header for all posts
        header = '<html><meta http-equiv="content-type" content="text/html; charset=' + ENCODING + '"/>'
        header += "<head><title>" + title + "</title></head><body>"
        header += "<h1>" + title + "</h1><h2>" + unescape(description) + "</h2>"

    # then find the total number of posts
    posts_tag = soup.find("posts")
    total_posts = int(posts_tag["total"])
    print(total_posts)
    # then get the XML files from the API, which we can only do with a max of 50 posts at once
    for i in range(start_post, total_posts, 50):
        # find the upper bound
        j = i + 49
        if j > total_posts:
            j = total_posts

        print("Getting posts " + str(i) + " to " + str(j) + ".")

        url = "http://" + account + TUMBLR_URL + "?num=50&start=" + str(i)
        try:
            time.sleep(5)
            response = urlopen(url)
            soup = BeautifulSoup(response.read(), PARSER)
            posts = soup.findAll("post")
            for post in posts:    
                savePost(post, save_folder, header=header)
        except Exception:
            import traceback
            logging.warning('generic exception: ' + traceback.format_exc())

    print("Backup Complete")


if __name__ == "__main__":

    account = None
    use_csv = False
    save_folder = None
    start_post = 0
    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            if arg.startswith("--"):
                option, value = arg[2:].split("=")
                if option == "csv" and value == "true":
                    use_csv = True
                if option == "save_folder":
                    save_folder = value
                if option == "start_post":
                    start_post = int(value)
            else:
                account = arg

    assert account, "Invalid command line arguments. Please supply the name of your Tumblr account."

    if (save_folder == None):
        save_folder = os.path.join(os.getcwd(), account)

    backup(account, use_csv, save_folder, start_post)
