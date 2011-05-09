import re
import datetime
import contextlib

from .utils import get_bill_detail_url, get_session_days_url, get_vote_history_url
from .utils import removeNonAscii, sponsorsToList

from billy.scrape import NoDataForPeriod, ScrapeError
from billy.scrape.bills import BillScraper, Bill
from billy.scrape.votes import Vote

import lxml.html

table_xpath = "/html/body/table/tbody/tr/td/div[@id='tablecontent']/table/tbody/tr/td[@class='content']/div[@id='votecontent']/div/div/table"

# Extracts bill number and title from a string
# Sample input "Something someting Bill 1: Bill Title - Something else "
#    returns (1,Bill Title)
def extract_title(string):
	title_pattern = re.compile(".* Bill (\d*):\s*(.*)\s*-.*$")
	g1 = title_pattern.search(string)
	#print 'g1 = ', g1
	if g1 != None:
		groups = g1.groups()
		#print 'groups ', groups
		if len(groups) == 2:
			bill_number = groups[0]
			title = groups[1].strip()
			#print "extract_title billn orig [%s] [%s] title [%s]" % (string, bill_number, title)
			return (bill_number, title )
	return (None,None)

# extracts senators from string.
#   Gets rid of Senator(s) at start of string, 
#   Senator last names are separated by commas, except the last two 
#   are separated by the word 'and'
#   handles ' and '
def xxxxcorrected_sponsor(orig):

	sponsors = []
	parts = orig.split()
	if orig.startswith("Senator") and len(parts) >= 2:
		#print '|', orig, '| returning ', parts[1]
		sponsors.append(" ".join(parts[1:]))
		return sponsors

	if len(parts) == 1:
		sponsors.append(parts[0])
		return sponsors

	#print 'orig ' , orig , ' parts ', len(parts)
	and_start = orig.find(" and ")
	if and_start > 0:
		#print 'has and |', orig, '|'
		for p in parts:
			if p != "and":
				sponsors.append(p)
		#print  ' returning ', sponsors 
		return sponsors
	
	else:
		sponsors.append(orig)

	return sponsors


# Returns a tuple with the bill id, sponsors, and blurb 
def extract_bill_data(data):

	chamber = "lower"
	pat1 = "<title>"
	match = data.find(pat1)

	title = None
	start_title = data.find("<title>")
	end_title = data.find("</title>")

	if start_title > 0 and end_title > start_title:
		start_title = start_title + len("<title>")
		title = data[start_title:end_title]
		#print 'before title is [', title, ']'
		(bill_number,title) = extract_title(title)
	else:
		return ()

	next_part = end_title + len("</title>")
	sample1 = data[next_part:]

	start_sponsor = sample1.find("Sponsors: ")
	if start_sponsor < 0:
		print 'warning no sponsors'
		return ()

	start_sponsor = start_sponsor + len("Sponsors:")
	sample1 = sample1[start_sponsor:]
	#print 'start sponsor: ' , start_sponsor 

	end_sponsor = sample1.find("<br>")
	#print 'end sponsor: ' , end_sponsor 
	if end_sponsor < 0:
		print 'warning no sponsors'
		return ()

	sponsor_names = sample1[:end_sponsor]
	if sponsor_names.find("Senator") >= 0:
		chamber = "upper"
	tmp = sponsor_names.split()
	sponsor_names = " ".join(tmp).split(",")

	slist = [corrected_sponsor(n) for n in sponsor_names]

	sponlist = []
	for bbb in slist:
		sponlist.extend(bbb)

	blurb = None
	bill_name = title
	return ( bill_number, bill_name, sponlist, blurb, chamber )



#################################################################
# main class:
class SCBillScraper(BillScraper):
    state = 'sc'

    @contextlib.contextmanager
    def lxml_context(self,url):
	body = self.urlopen(url)
	body = unicode(self.urlopen(url), 'latin-1')
	#body = body.replace('name=Expires', 'name="Expires"')
	elem = lxml.html.fromstring(body)
	#print "lxml_context() GOT ELEM\n"
	try:
		yield elem
	except Exception as error:
		print 'show error ', url , ' error ', error
		#self.show_error(url,body)	
		raise


    #################################################################
    # Return a list of bills found on this page
    def scrape_vote_page(self, chamber, page):
	self.log('scraping bill vote page for chamber %s' % chamber)
	bills_on_this_page = []
	bills_seen = set()

	tables = page.xpath(table_xpath)
	if len(tables) != 1:
		self.warn( 'error, expecting one table, aborting' )
		return

	rows = tables[0].xpath("//tr")
	numbills, dupcount = 0, 0
	session = "119"

	for r in rows:
	  try:
		item = {}
		alltd = r.xpath("td");
		brows = r.xpath("td[1]/a[@target='_blank']/text()")
		if len(brows) <= 0:
			continue

		bname = r.xpath("td[2]/a[@target='_blank']/text()")
		if len(bname) == 0:
			continue

		btitle = r.xpath("td[3]/text()")
		btitle1 = r.xpath("string(td[3])")
		
		title = btitle
		if len(btitle) == 0:
			title = btitle1
		else:
			title = " ".join(btitle)

		if title.startswith("(") and title.endswith(")"):
			title = title[1:-1]

		bdate = r.xpath("td[4]/text()")
		bcandidate = r.xpath("td[5]/text()")

		bayes = r.xpath("td[6]/text()")
		bnayes = r.xpath("td[7]/text()")
		bnv = r.xpath("td[8]/text()")
		excabs = r.xpath("td[9]/text()")
		abstain = r.xpath("td[10]/text()")
		total = r.xpath("td[11]/text()")
		result = r.xpath("td[5]/text()")

		bill_id = " ".join(bname)
		if bill_id in bills_seen:
			dupcount = dupcount + 1
		else:
			bills_seen.add( bill_id )
			numbills = numbills + 1

			bill = Bill(session,chamber, bill_id, title)
			bills_on_this_page.append(bill)
			bills_seen.add( bill_id )
			self.debug("   votepage: found bill |%s| |%s|", bill_id, title)
	  except UnicodeEncodeError:
		self.error("scrape vote page : unicode error")

	self.log( "THERE ARE %d bills: %d dups " %(numbills,dupcount)) 
	return bills_on_this_page


    ####################################################
    # scrape static bill html pages, urls are like 
    # http://scstatehouse.gov/sess119_2011-2012/bills/%d.htm
    def scrape_static_bill(self, billurl, session, data, summary_file):
	(bill_id,title,sponsors,blurb,chamber) = extract_bill_data(data)
	self.log("     %s:%s:%s:%s:%s" % (bill_id,title,chamber,sponsors,blurb))
	print "     %s:%s:%s:%s:%s" % (bill_id,title,chamber,sponsors,blurb)
	summary_file.write( "%s:%s:%s\n    %s\n" % (bill_id,title,chamber,sponsors))
	#summary_file.write( "%s:%s:%s:%s" % (bill_id,title,sponsors,blurb))
        bill = Bill(session, chamber, bill_id, title)
	bill.add_source(billurl)

	for sponsor in sponsors:
		bill.add_sponsor("sponsor", sponsor )
	return bill

    ###################################################
    def scrape_session_days(self, url, page):
	"""The session days page contains a list of 
	bills by introduction date.

	Find links which are of the form YYYYMMDD.htm (eg. 20110428.htm)
	Returns a list of these pages
	"""

	page = lxml.html.fromstring(page)
	self.log("scrape_session_days: getting list of day pages: [%s]" % url )
	page.make_links_absolute(url)

	# All the links have 'contentlink' class
	for link in page.find_class('contentlink'):
		self.debug( "   Bills introduced on %s are at %s" % ( str(link.text),str(link.attrib['href']) ))
	return [str(link.attrib['href']) for link in page.find_class('contentlink')]


    ###################################################
    def extract_bill_info(self, session,chamber,d):
	"""Extracts bill info, which is the bill id,
	the sponsors, and a paragraph describing the bill (a shorter
	summary suitable for a title may be available 
	elsewhere, but not here).

	Returns: a Bill with bill id, sponsor, and title set."""

	regexp = re.compile( "/cgi-bin/web_bh10.exe" )
	bregexp = re.compile( "bill1=(\d+)&" )

	bill_name = None
	sponsors_str = None
	summary = None
	the_action = None

	start = d.find("--")
	stop = d.find(":",start)

	d1 = d
	after_sponsor = d
	splist = []

	maybe_actions = ""
	#print "   sp (%d,%d)" % (start , stop)
	if start >= 0 and stop > start:
		bn = d[:start]
		start += 2  # skip the two dashes
		bill_name = bregexp.search(bn).groups()[0]
		#print 'bill_name ', bill_name
		self.debug( "\nbill_name |%s|" % bill_name )

		sponsors_str = d[start:stop]
		self.debug( "\nsponsors_str |%s|" %  sponsors_str)
		splist = sponsorsToList(sponsors_str)
		self.debug( "\nafter cleansing |%s|\n\n" %  ("|".join(splist)))

		after_sponsor = d[stop+1:]

	summary = d1 
	d1_end = after_sponsor.find("<br>",stop)
	if d1_end > 0:
		summary = d1[stop:d1_end]

		d1 = d1[:d1_end]
		maybe_actions = d
		#print "AAAAA WHATEVER ", maybe_actions
		act = maybe_actions.find("<center>")
		#print "    cter?  ", act
		if act != -1:
			end_act = maybe_actions.index("</center>", act)
			act += len("<center>")
			maybe_actions = maybe_actions[act:end_act]
			#print "Action: ", maybe_actions
			the_action = maybe_actions


	try:
		bs = summary.decode('utf8')
	except:
		self.log("scrubbing %s summary, originally %s" % (bill_name,summary) )
		summary = removeNonAscii(summary)

	#print "==> [%s] Sponsors [%s] Summary [%s]\n\n" % (bill_name, sponsors_str, summary)
	
	if chamber == "lower":
		bill_prefix  = "H "
		bill_id = "H %s" % bill_name
	else:
		bill_prefix  = "S "
		bill_id = "S %s" % bill_name

	bill = Bill(session,chamber,bill_id,summary)
	for sponsor in splist:
		bill.add_sponsor("primary", sponsor )

	#TEMPORARY TAMI
	#if the_action != None:
	#	bill.add_action(chamber, the_action, 'date')
	return bill

    ###################################################
    def scrape_day(self, session,chamber,data):
	"""Extract bill info from the daily summary
	page.  Splits the page into the different
	bill sections, extracts the data,
	and returns list containing the parsed bills.
	"""

	# throw away everything before <body>
	start = data.index("<body>")
	stop = data.index("</body>",start)

	if stop >= 0 and stop > start:
	  all = re.compile( "/cgi-bin/web_bh10.exe" ).split(data[start:stop])
	  #print "number of bills page = %d" % (len(all)-1)
	  self.log( "number of bills page = %d" % (len(all)-1 ))

	  # skip first one, because it's before the pattern
	  return [self.extract_bill_info(session,chamber,segment) 
		for segment in all[1:]]

	print 'bad format'
	raise

    ####################################################
    # 1. Get list of days with information by parsing daily url
    #    which will have one link for each day in the session.
    # 2. Scan each of the days and collect a list of bill numbers.
    # 3. Get Bill info.
    ####################################################
    def scrape(self, chamber, session):
	self.log( 'scrape(session %s,chamber %s)' % (session, chamber))

        if session != '119':
            raise NoDataForPeriod(session)

        sessions_url = get_session_days_url(chamber) 

	session_days = []
	with self.urlopen( sessions_url ) as page:
		session_days = self.scrape_session_days(sessions_url,page)

	self.log( "Session days: %d" % len(session_days) )

	bills_with_votes = []
	with self.lxml_context( get_vote_history_url(chamber) ) as page:
		bills_with_votes = self.scrape_vote_page(chamber,page)

	self.log( "Bills with votes: %d" % len(bills_with_votes))
	
	bill_ids_with_votes = [b['bill_id'] for b in bills_with_votes]
	bills_with_summary = set(bill_ids_with_votes)
				

	# now go through each session day and extract the bill summaries
	# if the vote page has a bill summary, use that for the title
	# otherwise, use the longer paragraph on the day page
	#
	# keep track of which bills have been processed, and get bill details only once
	# (each bill will appear on the day page whenever it had an action)
	numdays = 0
	bills_processed = set()
	billdict = dict()
	for b in bills_with_votes:
		billdict[ b['bill_id'] ] = b

	for dayurl in session_days:
		self.debug( "processing day %s" % dayurl )
		with self.urlopen( dayurl ) as data:
			daybills = self.scrape_day(session,chamber,data)
			self.debug( "  #bills on this day %d" % len(daybills))
			for b in daybills:
				bill_id = b['bill_id']
				if bill_id in bills_processed: 
					self.debug("   already processed %s" % bill_id )
					continue

				self.debug( "    processing %s ... " % bill_id )
				if bill_id in bills_with_summary:
					ab = billdict[bill_id]
					self.debug( "  changing title to %s" % ab['title'])
					b['description'] = b['title']
					b['title'] = ab['title']

				bills_processed.add( b['bill_id']  )
				self.save_bill(b)

			
		numdays += 1

	self.log( "Total bills processed: %d : " % len(bills_processed) )
	self.debug( "Bills processed: %s" % ("|".join(bills_processed)) )



# example title: <title>2011-2012 Bill 1: S.C. Election Reform Act - South Carolina Legislature Online</title>
#########################################################################
def scrape_bill_name(page):
	#log('scraping bill name')

	title = page.xpath("/html/head/title/text()")[0].split(":",1)[1].split("-",1)[0]
	billname = page.xpath("/html/body/p/b")[0].text
	if billname.startswith("S"):
		chamber = "upper"
	else:
		chamber = "lower"
	return (title,billname,chamber)

