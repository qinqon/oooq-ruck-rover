#!/bin/env python
import requests
import re
import pprint
import json
import irc.client
import itertools
import sys
import feedparser

import pandas as pd
import numpy as np

from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from launchpadlib.launchpad import Launchpad

infra_status_regexp = re.compile('^ *([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}) *UTC *(.+)$')
failing_check_jobs = re.compile('^FAILING CHECK JOBS: .*')
sova_status_table = re.compile('.*arrayToDataTable\((\[.*\])\);.*', re.DOTALL)
sova_overall_job_name = re.compile('.*.*function (.*)_overall.*')

infra_status_url = 'https://wiki.openstack.org/wiki/Infrastructure_Status'
upstream_zuul_url = 'http://zuul.openstack.org/status'
rechecks_url = 'http://status.openstack.org/elastic-recheck/data/all.json'
sova_gate_status_url = 'http://cistatus.tripleo.org/gates/'
rhos_dashboard_url = 'http://rhos-release.virt.bos.redhat.com:3030/events'
gate_failures_url = 'http://www.rssmix.com/u/8262477/rss.xml'

infra_status_utc_format = '%Y-%m-%d %H:%M:%S'

cachedir = "/home/ellorent/.launchpadlib/cache/"

pd.set_option('display.max_colwidth', -1)

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

def get_upstream_tripleo_gate():
    upstream_zuul = json.loads(requests.get(upstream_zuul_url).content) 
    gate_queues = next(pipeline['change_queues'] for pipeline in upstream_zuul['pipelines'] if pipeline['name'] == 'gate')
    tripleo_heads = next(queue for queue in gate_queues if queue['name'] == 'tripleo')['heads']
    tripleo_queue = []
    if tripleo_heads:
        tripleo_queue = [0]
    return pd.DataFrame(tripleo_queue)

def get_upstream_tripleo_bugs():
    launchpad = Launchpad.login_anonymously('OOOQ Ruck Rover', 'production', cachedir, version='devel')
    project = launchpad.projects['tripleo']

    # We can filter by status too 
    bugs = project.searchTasks()
    
    return bugs

def get_irc_gate_status():
    client = irc.client.Reactor()
    server = client.server()
    failing_jobs = [""]

    def on_connect(connection, event):
        connection.join('#oooq')
    
    def on_join(connection, event):
        connection.privmsg('#oooq', '!gatestatus')

    def on_disconmnect(connection, event):
        raise SystemExit()
    
    def on_public_message(connection, event):
        message = event.arguments[0]
        # TODO: Check it's hubbot
        if failing_check_jobs.match(message):
            failing_jobs[0] = message
            connection.quit("Using irc.client.py")

    try:
        server.connect("chat.freenode.net", 6667, "ruck-rover-bot")
    except irc.client.ServerConnectionError:
        print(sys.exc_info()[1])
        raise SystemExit(1)
    
    client.add_global_handler("welcome", on_connect)
    client.add_global_handler("join", on_join)
    client.add_global_handler("disconnect", on_disconmnect)
    client.add_global_handler("pubmsg", on_public_message)

    try:
        client.process_forever()
    except SystemExit:
        print('END')

    return failing_jobs[0]

def get_gate_failures():
    return pd.DataFrame(feedparser.parse(gate_failures_url)['entries'])

def get_rechecks():
    rechecks = json.loads(requests.get(rhos_dashboard_url).content)['buglist']
    return rechecks

def get_sova_gate_status():
    sova_gate_status = requests.get(sova_gate_status_url) 
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
    print('get_rhos_dashboard')
    dashboard_data = []
    with requests.get(rhos_dashboard_url, stream=True) as response:
        for line in response.iter_lines():
            #We don't care about the "end" entries so we stop at them
            if "\"end\"" in line:
                break
            if line:
                dashboard_data.append(json.loads(line.replace("data: ", "")))
    return dashboard_data

def get_full_status():
    status = {}
    
    # TODO: Parallelize gathering of information
    status['infra-issues'] = get_infra_issues()
    status['upstream-tripleo-gate'] = get_upstream_tripleo_gate()
    #status['upstream-tripleo-bugs'] = get_upstream_tripleo_bugs()
    #status['gate-status'] = get_irc_gate_status()
    #status['gate-failures'] = get_gate_failures()
    #status['rechecks'] = get_rechecks()
    #status['sova-gate-status'] = get_sova_gate_status()
    #status['rhos-dashboard'] = get_rhos_dashboard()
    
    return status

def get_todays_week_range():

    today = datetime.now()
    start = today - timedelta(days=today.weekday())
    end = start + timedelta(days=6)
    return (start, end)

def analyze_infra_issues(infra_issues):
    print("Openstack infra new issues:")
    week_start, week_end = get_todays_week_range()
    # TODO: Print week's ones
    print(infra_issues.head())

def analyze_upstream_tripleo_gate(gate_queue):
    print("Upstream tripleo gate queue:")
    print(gate_queue)

# TODO: Use logstash or pandas ?
def analyze_status(status):
    analyze_infra_issues(status['infra-issues'])
    analyze_upstream_tripleo_gate(status['upstream-tripleo-gate'])

def main():
    tripleo_status = get_full_status()
    analyze_status(tripleo_status)

if __name__ == '__main__':
    main()
