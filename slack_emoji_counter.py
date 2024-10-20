import argparse
import requests
import re
import csv
import time

CONVERSATION_LIST_URL = "https://slack.com/api/conversations.list"
CONVERSATION_HISTORY_URL = "https://slack.com/api/conversations.history"
CONVERSATION_REPLY_URL = "https://slack.com/api/conversations.replies"
EMOJI_LIST_URL = "https://slack.com/api/emoji.list"
CHANNEL_METADATA = ["id", "name"]

class EmojiCounter:
  def __init__(self, token):
    self.HEADER = {
      "Authorization": f"Bearer {token}",
      "Content-Type": "application/x-www-form-urlencoded"
    }

    self._channels = []
    self._custom_emoji_set = set()
    self._alias_dict = dict() # (emoji, 원래 emoji)의 dict
    self._emoji_info = dict()

  def _api_call_with_retries(self, url, params=None, retries=100) -> dict:
    """
    slack API를 호출함.
    호출 횟수 제한 초과로 실패한 경우 정해진 횟수만큼 재시도함.

    Args:
      url (str): 호출할 URL
      params (dict): API 호출 시 설정할 parameter
      retries (int): 재시도할 횟수

    Returns:
      dict: API 호출에 성공한 경우 response의 json을, 실패한 경우 빈 dictionary를 return
    """
    
    for attempt in range(retries):
      if params is None:
        response = requests.get(url, headers=self.HEADER)
      else:
        response = requests.get(url, headers=self.HEADER, params=params)
      
      data = response.json()
      if data["ok"] == True:
        return data
      # Slack은 1분 동안 특정 API에 대한 호출 횟수에 제한이 있고, 이 경우 ratelimited 에러가 발생
      elif data["error"] == "ratelimited":
        print(f"과도한 요청으로 5초 대기 ({attempt+1} / {retries})")
        time.sleep(5)
      else:
        print(f"Error: {data['error']}")
        break
    
    # API call에 실패한 경우 빈 dictionary return
    return dict()

  def _count_inline_emoji(self, emoji):
    if emoji in self._alias_dict:
      emoji = self._alias_dict[emoji]

    if emoji not in self._emoji_info:
      self._emoji_info[emoji] = {
        "inline": 0,
        "reaction": 0,
        "unique_reaction": 0
      }

    self._emoji_info[emoji]["inline"] += 1

  def _count_reaction_emoji(self, emoji, cnt):
    if emoji in self._alias_dict:
      emoji = self._alias_dict[emoji]

    if emoji not in self._emoji_info:
      self._emoji_info[emoji] = {
        "inline": 0,
        "reaction": 0,
        "unique_reaction": 0
      }

    self._emoji_info[emoji]["reaction"] += cnt
    self._emoji_info[emoji]["unique_reaction"] += 1
    
  def check_token_is_valid(self) -> bool:
    for url in [CONVERSATION_LIST_URL, EMOJI_LIST_URL]:
      response = requests.get(url, headers=self.HEADER)
      data = response.json()
      
      if data["ok"] == False:
        return False
      
    return True

  def get_channel_list(self) -> list:
    params = {
      'limit': 1000
    }
    
    # 1000개를 넘는 채널이 있는 경우 여러 번 호출하여 전체 채널 목록을 불러옴
    while True:
      json = self._api_call_with_retries(CONVERSATION_LIST_URL, params=params)

      for channel in json["channels"]:
        channel_info = dict()
        for key in CHANNEL_METADATA:
          channel_info[key] = channel[key]
          
        self._channels.append(channel_info)
        
      cursor = json.get('response_metadata', {}).get('next_cursor')
      
      if not cursor:
        break
      
      params['cursor'] = cursor

    print(f"공개 채널 수: {len(self._channels)}")

  def get_custom_emoji_list(self) -> list:
    json = self._api_call_with_retries(EMOJI_LIST_URL)

    for name, url in json["emoji"].items():
      if len(url) > 5 and url[:6] == "alias:":
        self._alias_dict[name] = url[6:]
        continue # alias인 경우 alias 목록에만 넣고 이모지 개수를 추가하진 않음

      self._custom_emoji_set.add(name)

    print(f"커스텀 이모지 수: {len(self._custom_emoji_set)}")

  def count_emoji(self):
    """
    모든 채널의 대화에 대해 글에 적힌 inline 이모지와 반응으로 달린 reaction 이모지의 개수를 셈.
    답글이 있는 경우 답글에 있는 inline, reaction 이모지도 셈.
    Also sent to channel (thread broadcast)한 답글의 경우 broadcast된 메시지에서는 세지 않고, 답글에서만 세어 중복을 방지함.
    skin tone만 다른 이모지를 하나의 이모지로 취급함.
    """
    
    for idx, channel in enumerate(self._channels):
      params = {
        'channel': channel["id"],
        'limit': 1000
      }

      print(f'[{idx+1}/{len(self._channels)}] {channel["name"]} 처리 시작')

      # 1000개를 넘는 메시지가 있는 경우 여러 번 호출하여 전체 메시지를 불러옴
      parent_message_list = []
      while True:
        json = self._api_call_with_retries(CONVERSATION_HISTORY_URL, params=params)

        if "messages" not in json:
          continue

        parent_message_list = parent_message_list + json["messages"]
        
        cursor = json.get('response_metadata', {}).get('next_cursor')
        
        if not cursor:
          break
        
        params['cursor'] = cursor
      
      print(f'[{idx+1}/{len(self._channels)}] {channel["name"]} 메시지 개수: {len(parent_message_list)}')

      for parent_message in parent_message_list:
        # also sent to channel한 답글의 경우 이후에 reply에서 검사할 것이므로 생략
        if "subtype" in parent_message and parent_message["subtype"] == "thread_broadcast":
          continue

        # Reply가 없는 message의 경우 parent message만 parsing
        if "reply_count" not in parent_message:
          msg_list = [parent_message]
        # Reply가 있는 message의 경우 reply를 포함한 message를 parsing
        else:
          reply_req_params = {
            'channel': channel["id"],
            'ts': parent_message["ts"]
          }
          reply_json = self._api_call_with_retries(CONVERSATION_REPLY_URL, params=reply_req_params)
          msg_list = reply_json["messages"]

        for message in msg_list:
          # Inline 이모지 수
          if "text" in message:
            text = message["text"]
            pattern = r":[a-z0-9_\-+]+:"
            emoji_list = re.findall(pattern, text) # :text: 형태의 문자 개수를 셈

            for emoji_raw in emoji_list:
              emoji = emoji_raw[1:-1]
              if len(emoji) == 0:
                continue
              self._count_inline_emoji(emoji)

          # Reaction 이모지 수
          if "reactions" in message:
            for reaction in message["reactions"]:
              emoji = reaction["name"].split('::')[0] # skin tone만 다른 이모지는 같은 이모지 취급
              self._count_reaction_emoji(emoji, reaction["count"])
  
  def print_stat(self):
    """
    emoji_usage.csv에 이모지 사용량 정보를 출력함.
    - Emoji: 이모지 이름
    - is_custom: 커스텀 이모지 여부
    - reaction: reaction 이모지로 눌린 횟수
    - unique_reaction: reaction 이모지로 사용된 횟수
      (한번에 여러 명이 reaction한 경우 하나로 카운팅)
    - inline: 글에 사용된 이모지 횟수
    - total: 이모지로 사용된 횟수 (unique_reaction + inline)
    
    unused_emoji.csv에는 inline + reaction으로 사용되지 않은 이모지 목록을 출력함.
    """
    
    with open('emoji_usage.csv', 'w') as f:
      writer = csv.writer(f)
      writer.writerow(["Emoji",
                       "is_custom",
                       "reaction",
                       "unique_reaction",
                       "inline",
                       "total"])

      for emoji, info in self._emoji_info.items():
        writer.writerow([':' + emoji + ':',
                         emoji in self._custom_emoji_set,
                         info["reaction"],
                         info["unique_reaction"],
                         info["inline"],
                         info["unique_reaction"] + info["inline"]])

        if emoji in self._custom_emoji_set:
          self._custom_emoji_set.remove(emoji)

    with open('unused_emoji.csv', 'w') as f:
      writer = csv.writer(f)
      for emoji in self._custom_emoji_set:
        writer.writerow([':' + emoji + ':'])
    
    print(f'안 쓰는 커스텀 이모지 수: {len(self._custom_emoji_set)}')

if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument('-t', '--token', type=str, required=True)
  args = parser.parse_args()

  ec = EmojiCounter(args.token)
  
  if not ec.check_token_is_valid():
    print(f'토큰이 유효하지 않습니다')
    raise ValueError()
  
  ec.get_channel_list()
  ec.get_custom_emoji_list()
  ec.count_emoji()
  ec.print_stat()