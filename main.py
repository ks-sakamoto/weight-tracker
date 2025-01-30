import hashlib
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

import firebase_admin
import streamlit as st
from firebase_admin import credentials, db

from components import DateRangeSelector, WeightInputForm, WeightRecordEditor
from database import WeightDatabase
from visualization import WeightVisualizer

# Firebaseの初期化
if not firebase_admin._apps:
    cred = credentials.Certificate(".streamlit/secrets.json")
    firebase_admin.initialize_app(
        cred, {"databaseURL": st.secrets["app"]["database_url"]}
    )


def get_device_id() -> str:
    """
    デバイスIDを取得する

    Returns
    -------
    str
        デバイスの一意識別子。存在しない場合は新規生成する。
    """
    if "device_id" not in st.session_state:
        # セッションにデバイスIDがない場合、ローカルストレージから取得を試みる
        st.session_state["device_id"] = str(uuid.uuid4())
    return st.session_state["device_id"]


def hash_pasword(password: str) -> str:
    """
    パスワードをハッシュ化する

    Parameters
    ----------
    password : str
        ハッシュ化するパスワード

    Returns
    -------
    str
        ハッシュ化されたパスワード
    """
    return hashlib.sha256(password.encode()).hexdigest()


def verify_device(device_id: str) -> Optional[Dict[str, Any]]:
    """
    デバイスIDが登録済みか確認する

    Parameters
    ----------
    device_id : str
        確認するデバイスID

    Returns
    -------
    Optional[Dict[str, Any]]
        登録済みの場合はユーザー情報、未登録の場合はNone
    """
    ref = db.reference("devices")
    devices = ref.get() or {}
    return devices.get(device_id)


def register_device(device_id: str, user_type: str, password: str) -> bool:
    """
    新しいデバイスを登録する

    Parameters
    ----------
    device_id : str
        登録するデバイスのID
    user_type : str
        ユーザータイプ（secrets["app"]["user_type"])
    password : str
        設定するパスワード

    Returns
    -------
    bool
        登録成功の場合True、失敗の場合False
    """
    try:
        ref = db.reference("devices")
        devices = ref.get() or {}

        # すでに同じユーザータイプが登録されていないか確認
        for device in devices.values():
            if device["user_type"] == user_type:
                False

        devices[device_id] = {
            "user_type": user_type,
            "password": hash_pasword(password),
            "registerd_at": datetime.now().isoformat(),
        }
        ref.set(devices)
        return True
    except Exception as e:
        st.error(f"デバイス登録エラー: {str(e)}")
        return False


def authenticate(device_id: str, password: str) -> bool:
    """
    ユーザー認証を行う

    Parameters
    ----------
    device_id : str
        認証するデバイスID
    password : str
        認証パスワード

    Returns
    -------
    bool
        認証成功の場合True、失敗の場合False
    """
    device_info = verify_device(device_id)
    if device_info and device_info["password"] == hash_pasword(password):
        st.session_state["user_type"] = device_info["user_type"]
        return True
    return False


def login_page():
    """
    ログインページを表示する
    """
    st.title("体重管理アプリ - ログイン")

    device_id = get_device_id()
    st.write(f"デバイスID: {device_id}")

    # 未登録デバイスの場合、登録フォームを表示
    if not verify_device(device_id):
        st.subheader("新規デバイス登録")
        user_type = st.selectbox(
            "ユーザータイプ", st.secrets["app"]["user_type"]
        )
        password = st.text_input("パスワード", type="password")

        if st.button("デバイスを登録"):
            if register_device(device_id, user_type, password):
                st.success("デバイスが登録されました")
                st.rerun()
            else:
                st.error("デバイス登録に失敗しました")

    # 登録済みデバイスの場合、ログインフォームを表示
    else:
        password = st.text_input("パスワード", type="password")

        if st.button("ログイン"):
            if authenticate(device_id, password):
                st.session_state["logged_in"] = True
                st.success("ログインに成功しました")
                st.rerun()
            else:
                st.error("パスワードが正しくありません")


def init_session_state():
    """
    セッション状態を初期化する
    """
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False
    if "user_type" not in st.session_state:
        st.session_state["user_type"] = None


def main():
    """
    メインアプリケーション
    """
    init_session_state()

    if not st.session_state["logged_in"]:
        login_page()
        return

    st.title("体重管理アプリ")
    st.write(f"ログインユーザー: {st.session_state['user_type']}")

    # データベースインスタンスの作成
    db = WeightDatabase(st.session_state["user_type"])

    # サイドバーに入力フォームを配置
    with st.sidebar:
        weight_form = WeightInputForm(db)
        weight_form.render()

        # 予測表示の切り替え
        show_prediction = st.checkbox("予測表示", value=False)

    # メイン画面に期間選択と記録表示
    start_date, end_date = DateRangeSelector.render()

    # 両ユーザーのデータを取得
    db1 = WeightDatabase(st.secrets["app"]["user_type"][0])
    db2 = WeightDatabase(st.secrets["app"]["user_type"][1])
    records1 = db1.get_records()  # 期間指定なしで全データを取得
    records2 = db2.get_records()

    # グラフの表示
    visualizer = WeightVisualizer(
        records1, records2, start_date, end_date, show_prediction
    )
    visualizer.render()

    # 現在のユーザーの記録のみ編集可能
    current_db = WeightDatabase(st.session_state["user_type"])
    current_records = [
        r
        for r in (
            db1
            if st.session_state["user_type"]
            == st.secrets["app"]["user_type"][0]
            else db2
        ).get_records()
        if start_date <= r.timestamp <= end_date
    ]
    editor = WeightRecordEditor(current_db, current_records)
    editor.render()

    if st.button("ログアウト"):
        st.session_state["logged_in"] = False
        st.session_state["user_type"] = None
        st.rerun()


if __name__ == "__main__":
    main()
