# [updater.py 파일 맨 아래 알림 전송 함수를 이 이메일 코드로 교체해 주세요]

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_email_notification(lotto_combs, pension_combs, latest_lotto, latest_pension):
    # 깃허브 Secrets에서 메일 설정 정보 로드
    sender_email = os.environ.get('SENDER_EMAIL')      # 보내는 구글 메일 주소
    sender_password = os.environ.get('SENDER_PASSWORD')  # 구글 앱 비밀번호 (16자리)
    receiver_email = os.environ.get('RECEIVER_EMAIL')  # 받는 네이버 메일 주소
    
    if not sender_email or not sender_password or not receiver_email:
        print("[Warning] 메일 인증 정보가 없어 발송을 건너뜁니다.")
        return

    # 1. 메일 제목 및 본문 조립 (HTML 형식으로 깔끔하게 가독성 상향)
    subject = f"🎰 [IDS 엔진] 로또 {latest_lotto + 1}회 / 연금복권 {latest_pension + 1}회 추천 번호"
    
    body = f"""
    <h3>📊 이번 주 IDS 로터리 분석 시스템 추천 결과</h3>
    <p>본 메일은 추첨 데이터 전수조사 배치 완료 후 자동 발송된 메시지입니다.</p>
    <hr>
    <h4>🎰 로또 제 {latest_lotto + 1}회차 추천 세트</h4>
    <ul>
    """
    for i, comb in enumerate(lotto_combs, 1):
        body += f"<li><b>{i}세트:</b> {', '.join(map(str, comb))}</li>"
        
    body += f"""
    </ul>
    <br>
    <h4>🎯 연금복권 제 {latest_pension + 1}회차 추천 (1~5조 공통)</h4>
    <ul>
        <li><b>조합 1:</b> {pension_combs[0]}</li>
        <li><b>조합 2:</b> {pension_combs[1]}</li>
    </ul>
    <hr>
    <p>지정된 번호들의 가중치 튜닝이 완벽히 적용되었습니다. 이번 주 기분 좋은 당첨을 응원합니다! 👍</p>
    """

    # 2. 메일 객체 생성
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'html', 'utf-8')) # HTML 포맷 지정

    # 3. 구글 SMTP 서버를 통한 실제 발송 처리
    try:
        # Gmail SMTP 표준 포트 587 및 TLS 보안 연결
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls() 
        server.login(sender_email, sender_password) # 인증 로그온
        
        server.sendmail(sender_email, receiver_email, msg.as_string())
        server.quit()
        print("[System] 네이버 메일로 추천 번호 발송 성공!")
    except Exception as e:
        print(f"[Error] 메일 발송 중 오류 발생: {e}")
