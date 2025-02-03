import json
import requests
import boto3
import traceback
import re
from datetime import datetime, timedelta, timezone

sns_client = boto3.client('sns')
ssm_client = boto3.client('ssm')
sns_topic_arn = "arn:aws:sns:us-east-1:419976789706:warframe"
event_freshness_threshold_min = 10

def check_event_freshness(start_time):
    if not start_time or start_time == "":
        return False
    start_time = datetime.strptime(start_time[:-5]+"+00:00", "%Y-%m-%dT%H:%M:%S%z")
    
    fresh_start_time = datetime.now(timezone.utc) - timedelta(minutes=event_freshness_threshold_min)
    if fresh_start_time < start_time:
        print(f"{start_time} is fresh!")
        return True
    else:
        return False

def run_warframe_alerts():
    res = requests.get(url="https://api.warframestat.us/pc")
    res = res.json()
    #check invasions
    invasions = res.get("invasions", [])
    ignored_rewards = ["detonite injector", "fieldron", "mutagen mass", "mutalist alad v nav coordinate"]
    qualifying_rewards = []
    for invasion in invasions:
        invasion_start_time = invasion.get("activation", "")
        if invasion_start_time == "" or not check_event_freshness(invasion_start_time):
            continue
        for party in ["attacker", "defender"]:
            rewards = invasion.get(party, {}).get("reward", {}).get("countedItems",[])
            for reward in rewards:
                reward_name = reward.get("key","").strip().lower()
                if reward_name != "" and reward_name not in ignored_rewards:
                    qualifying_rewards.append((reward_name,reward.get("count",-1)))
    if len(qualifying_rewards) > 0:
        invasion_msg = f"Invasions:\n{json.dumps(qualifying_rewards,indent=4)}"
        sns_client.publish(
            TopicArn=sns_topic_arn,
            Subject="Warframe Helper - Invasions",
            Message=invasion_msg
            )

    #check alerts
    alerts = res.get("alerts", [])
    fresh_alerts = []
    fresh_alert_flag = False
    if len(alerts) > 0:
        for a in alerts:
            if a['active'] and check_event_freshness(a['activation']):
                fresh_alert_flag = True
                fresh_alerts.append(a)
        if fresh_alert_flag:
            alert_msg = json.dumps(fresh_alerts, indent=4)
            sns_client.publish(
            TopicArn=sns_topic_arn,
            Subject="Warframe Helper - New Alerts",
            Message=alert_msg
            )

    # check for disruption fissure for void traces farming
    fissures = res.get('fissures', [])
    disruption_fissures = []
    mars_disruption_fissure_flag = False
    for f in fissures:
        if "disruption" in f.get('missionType', "").lower() and check_event_freshness(f['activation']):
            disruption_fissures.append(f)
            if "(Mars)" in f.get('node', ""):
                print(f"found fissure {f}")
                mars_disruption_fissure_flag = True
    print(json.dumps(disruption_fissures, indent=4))
    if mars_disruption_fissure_flag and len(disruption_fissures) > 0:
        fissures_msg = json.dumps(disruption_fissures, indent=4)
        sns_client.publish(
        TopicArn=sns_topic_arn,
        Subject="Warframe Helper - New Disruption Fissures",
        Message=fissures_msg
        )


def lambda_handler(event, context):
    #check drop updates from forum
    del event, context
    try:
        run_warframe_alerts()
    except Exception as e:
        sns_client.publish(
        TopicArn=sns_topic_arn,
        Subject="Warframe Helper Failed",
        Message=traceback.format_exc()
        )
        
    return {
        'statusCode': 200,
        'body': json.dumps('Hello from Lambda!')
    }
