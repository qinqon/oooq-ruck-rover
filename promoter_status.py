#!/bin/env python
import requests
import re
import json
import itertools
import sys
import os
#import feedparser

from datetime import timedelta

import pandas as pd
import numpy as np

from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from time import time
from launchpadlib.launchpad import Launchpad

infra_status_regexp = re.compile('^ *([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}) *UTC *(.+)$')
failing_check_jobs = re.compile('^FAILING CHECK JOBS: .*')
sova_status_table = re.compile('.*arrayToDataTable\((\[.*\])\);.*', re.DOTALL)
sova_overall_job_name = re.compile('.*.*function (.*)_overall.*')

promoter_skipping_log = re.compile('.*promoter Skipping promotion of (.*) to (.*), missing successful jobs:(.*)')
promoter_trying_to = re.compile('.*promoter Trying to promote (.*) to (.*)')

infra_status_url = 'https://wiki.openstack.org/wiki/Infrastructure_Status'
upstream_zuul_url = 'http://zuul.openstack.org/status'
rdo_zuul_url = 'https://review.rdoproject.org/zuul/status.json'
rechecks_url = 'http://status.openstack.org/elastic-recheck/data/all.json'
sova_status_url = 'http://cistatus.tripleo.org'
sova_gate_status_url = sova_status_url + '/gates/'
sova_promotion_status_url = sova_status_url + '/promotion/'
rhos_dashboard_url = 'http://rhos-release.virt.bos.redhat.com:3030/events'
gate_failures_url = 'http://www.rssmix.com/u/8262477/rss.xml'

infra_status_utc_format = '%Y-%m-%d %H:%M:%S'

cachedir = "{}/.launchpadlib/cache/".format(os.path.expanduser('~'))

pd.set_option('display.max_colwidth', -1)

tipboard_api_key = 'a26f7553d6f240c89083fd2c12284490'
tipboard_push_url="http://localhost:7272/api/v0.1/{}/push".format(tipboard_api_key)
tipboard_config_url="http://localhost:7272/api/v0.1/{}/tileconfig".format(tipboard_api_key)

def get_promoter_status(release_name):
    promoter_master_logs = requests.get("http://38.145.34.55/{}.log".format(release_name))    
    look_for_promotions = False
    status = {}
    last_promotion_name = ''
    last_promotion_status = 'noop'
    started_time = ''
    
    def get_log_time(log_line):
	log_line_splitted=log_line.split()
        log_time="{} {}".format(log_line_splitted[0], log_line_splitted[1])
	return log_time

    #FIXME: Optimize with a reversed sequence
    for log_line in reversed(list(promoter_master_logs.iter_lines())):
        if look_for_promotions: 
            if 'promoter STARTED' in log_line:
                started_time=get_log_time(log_line)
                break
            elif 'SUCCESS' in log_line:
                last_promotion_status = 'success'
            elif 'FAILURE' in log_line:
                last_promotion_status = 'failure'
            elif promoter_trying_to.match(log_line):
                #TODO: Not very efficient
                m = promoter_trying_to.match(log_line)
                initial_phase = m.group(1)
                target_phase = m.group(2)
                last_promotion_name = target_phase
                status[last_promotion_name] = last_promotion_status
                last_promotion_status = 'noop'
            elif promoter_skipping_log.match(log_line):
                last_promotion_status = 'skipped'

        elif 'promoter FINISHED' in log_line:
            look_for_promotions = True

	elif 'promoter STARTED' in log_line: 
       	    started_time=get_log_time(log_line)
            status = {'ongoing': 'Wait for the result'}
	    break
     
	elif 'ERROR    promoter' in log_line: 
       	    started_time=get_log_time(log_line)
            status = {'error': log_line.split('ERROR    promoter')[1]}
	    break
           				
    return (started_time, status)

def main():
    
    print(get_promoter_status(sys.argv[1]))

if __name__ == '__main__':
    main()
