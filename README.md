# Slack Emoji Counter
slack workspace의 public 채널에 있는 이모지 사용량 측정기

## Requirement
- Python 3.x
- 아래 3개 권한을 가진 Slack OAuth Access Token (xoxp- 로시작)
  - channels:history
  - channels:read
  - emoji:read

## Usage
```
python slack_emoji_counter.py -t xoxp-...
```
xoxp-...으로 되어있는 부분에 본인의 Slack OAuth Access Token을 써넣고 실행하면 된다.

### Output
- emoji_usage.csv: 이모지 사용량 정보
  - Emoji: 이모지 이름
  - is_custom: 커스텀 이모지 여부
  - reaction: reaction 이모지로 눌린 횟수
  - unique_reaction: reaction 이모지로 사용된 횟수
    (한번에 여러 명이 reaction한 경우 하나로 카운팅)
  - inline: 글에 사용된 이모지 횟수
  - total: 이모지로 사용된 횟수 (unique_reaction + inline)
- unused_emoji.csv: 사용되지 않은 커스텀 이모지