#!/bin/env python
import requests
import re
import json
import irc.client
import itertools
import sys
import feedparser
import jenkins

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
promoter_skipping_log = re.compile('promoter Skipping promotion of (.*) to (.*), missing successful jobs:(.*)')

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

cachedir = "/home/ellorent/.launchpadlib/cache/"

pd.set_option('display.max_colwidth', -1)

tipboard_api_key="082d554fbb964cf7ba168fbd25be11cb"
tipboard_push_url="http://localhost:7272/api/v0.1/{}/push".format(tipboard_api_key)
tipboard_config_url="http://localhost:7272/api/v0.1/{}/tileconfig".format(tipboard_api_key)
    
def to_infra_date(date_str):
    return datetime.strptime(date_str, infra_status_utc_format)

def get_infra_issues():
    infra_status = requests.get(infra_status_url) 
    infra_status_soup = BeautifulSoup(infra_status.content, 'html.parser')
    raw_issues = infra_status_soup.find_all('li')
    times = []
    issues = []
    for ts_and_issue in raw_issues:
        m = infra_status_regexp.match(ts_and_issue.get_text())
        if m:
            times.append(to_infra_date(m.group(1)))
            issues.append(m.group(2))
    time_and_issue = pd.DataFrame({ 'time': times, 'issue': issues})
    return time_and_issue.set_index('time')

def get_zuul_queue(zuul_status_url, pipeline_name, queue_name):
    zuul_status = json.loads(requests.get(zuul_status_url).content) 
    pipeline_queues = next(pipeline['change_queues'] for pipeline in zuul_status['pipelines'] if pipeline['name'] == pipeline_name)
    queue = pd.DataFrame()
    if pipeline_queues:
        found_queue = [queue for queue in pipeline_queues if queue['name'] == queue_name]
        if found_queue:
            queue_heads = found_queue[0]['heads']
            if queue_heads:
                queue = pd.DataFrame(queue_heads[0])
    return queue


def get_urgent_bugs():
    launchpad = Launchpad.login_anonymously('OOOQ Ruck Rover', 'production', cachedir, version='devel')
    project = launchpad.projects['tripleo']

    # We can filter by status too 
    bugs = project.searchTasks(tags='alert')
    return bugs

def get_gate_failures():
    return pd.DataFrame(feedparser.parse(gate_failures_url)['entries'])

def get_rechecks():
    rechecks = json.loads(requests.get(rechecks_url).content)['buglist']
    return pd.DataFrame.from_records(rechecks)

def get_sova_status(url):
    sova_gate_status = requests.get(url) 
    sova_gate_status_soup = BeautifulSoup(sova_gate_status.content, 'html.parser')
    scripts = sova_gate_status_soup.find_all('script')
    sova_status = {}
    for script in scripts:
        if 'ci_overall' in script.get_text():
            ci_overall = eval((re.findall(sova_status_table, script.string)[0]))
            sova_status['master-ci-overall'] = ci_overall
        elif '_overall' in script.get_text():
            job_name = re.findall(sova_overall_job_name, script.string)[0]
            job_status = eval((re.findall(sova_status_table, script.string)[0]))
            sova_status[job_name] = ci_overall
    return sova_status
 
def get_rhos_dashboard():
    dashboard_data = []
    with requests.get(rhos_dashboard_url, stream=True) as response:
        for line in response.iter_lines():
            #We don't care about the "end" entries so we stop at them
            if "\"end\"" in line:
                break
            if line:
                dashboard_data.append(json.loads(line.replace("data: ", "")))
    return dashboard_data

    #status['upstream-tripleo-bugs'] = get_upstream_tripleo_bugs()
    #status['gate-failures'] = get_gate_failures()
    #status['sova-gate-status'] = get_sova_gate_status()
    #status['rhos-dashboard'] = get_rhos_dashboard()
    
    return status

def get_oldest_zuul_job(queue):
    if 'enqueue_time' in queue:
        return queue.sort_values(by=['enqueue_time']).iloc[0]
    return pd.Series()

def get_minutes_enqueued(zuul_job):
    if not zuul_job.empty:
        current_time=int(time() * 1000)
        enqueue_time=zuul_job['enqueue_time']
        minutes_enqueued=((current_time - enqueue_time) / 60000)
        return minutes_enqueued
    else:
        return 0

def get_promoter_failures(release_name):
    promoter_master_logs = requests.get('http://38.145.34.55/master.log')    
    for log_line in reversed(promoter_master_logs.text):
        look_for_promotions = False
        if look_for_promotions: 
            m = re.match(promoter_skipping_log)
            if m:
                print(m.group(0))
                print(m.group(1))
                print(m.group(2))

        elif 'promoter FINISHED' in log_line:
            look_for_promotions = True
        elif 'promoter STARTED' in log_line:
            break


def format_enqueue_time(minutes_enqueued):
    if minutes_enqueued > 0:
        return "{} hours".format(str(timedelta(minutes=minutes_enqueued))[:-3])
    else:
        return "Empty"

def format_infra_issues(infra_issues):
    formatted = ""
    # TODO: Filter to interested issues
    for index, infra_issue in infra_issues.head().iterrows():
        formatted += "{} - {}<br>".format(str(index), infra_issue['issue'])
    return formatted

def format_rechecks(rechecks):
    limit = 5
    formatted = []
    for index, recheck in rechecks.head(limit).iterrows():
        bug_data = recheck['bug_data']
        if 'tripleo' in bug_data['affects']:
            formatted.append(bug_data['name'])
    return formatted

def format_bugs(bugs):
    formatted = []
    for bug in bugs:
        formatted.append({'label': "<a href='{}' target='_blank'>{}</a>".format(bug.web_link, bug.status), 'text': bug.title})
    return formatted

def update_tipboard_zuul_enqueue_time(status_url, pipeline_name, queue_name, tipboard_title, tipboard_key):
    queue = get_zuul_queue(status_url, pipeline_name, queue_name)
    oldest_job = get_oldest_zuul_job(queue)
    minutes_enqueued = get_minutes_enqueued(oldest_job)
    requests.post(tipboard_push_url, 
            data = {'tile': 'just_value', 
                    'key': tipboard_key, 
                    'data': json.dumps({'title': tipboard_title, 
                                        'description': "Enqueue time", 
                                        'just-value': format_enqueue_time(minutes_enqueued)})})
    if (minutes_enqueued > 420): # 7 hours
        config = {'just-value-color': 'red', 'fading_background':True}
    else:
        config = {'just-value-color': 'green', 'fading_background':False}
    
    requests.post("{}/{}".format(tipboard_config_url, tipboard_key), 
            data = { 
                'value': json.dumps(config)})
 
def main():
    # TODO: select with arguments what to show
    #analyze_zuul_queue("Openstack infra gate", 
    #        get_zuul_queue(upstream_zuul_url, pipeline_name='gate', queue_name='tripleo'))
    #analyze_zuul_queue("RDO infra periodic",
    #        get_zuul_queue(rdo_zuul_url, pipeline_name='openstack-periodic-24hr', queue_name='openstack-infra/tripleo-ci'))
    #analyze_rechecks(get_rechecks())
    periodic_queue = get_zuul_queue(rdo_zuul_url, pipeline_name='openstack-periodic-24hr', queue_name='openstack-infra/tripleo')
    oldest_periodic_job = get_oldest_zuul_job(periodic_queue)
    
    update_tipboard_zuul_enqueue_time(
        status_url=upstream_zuul_url, 
        pipeline_name='gate', 
        queue_name='tripleo', 
        tipboard_title='Tripleo gate', 
        tipboard_key='upstream_zuul')
 
    update_tipboard_zuul_enqueue_time(
        status_url=rdo_zuul_url, 
        pipeline_name='openstack-periodic-24hr', 
        queue_name='openstack-infra/tripleo', 
        tipboard_title='Tripleo periodic', 
        tipboard_key='rdo_zuul')
    
    
    requests.post(tipboard_push_url, 
            data = {'tile': 'fancy_listing', 
                    'key':'urgent_bugs', 
                    'data': json.dumps(format_bugs(get_urgent_bugs()))})
    
    requests.post(tipboard_push_url, 
            data = {'tile': 'text', 
                    'key':'infra_issues', 
                    'data': json.dumps({'text': str(format_infra_issues(get_infra_issues()))})})
    requests.post(tipboard_config_url + '/infra_issues', 
            data = { 
                    'value': json.dumps({'font_size': 23})})
    
    requests.post(tipboard_push_url, 
            data = {'tile': 'listing', 
                    'key':'elastic_rechecks', 
                    'data': json.dumps({'items': format_rechecks(get_rechecks())})})
   

if __name__ == '__main__':
    main()
