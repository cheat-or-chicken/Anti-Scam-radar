"""在終端機測試目前 SYSTEM_PROMPT 下的 RAG 對話品質。

使用前請先執行一次：python build_index.py
執行：python chat_cli.py
"""

from __future__ import annotations

from ollama_api import OllamaAPIError
from rag_client import roleplay_rag


def get_result(action) -> dict | None:
    try:
        return action()
    except FileNotFoundError as error:
        print(f"\n錯誤：{error}\n")
    except OllamaAPIError as error:
        print(f"\nOllama API 錯誤：{error}\n")
    except Exception as error:
        print(f"\n發生未預期錯誤：{error}\n")
    return None


def show_turn(result: dict) -> None:
    print(f"\nRAG AI：\n{result['answer']}")
    print()


def main() -> None:
    history: list[dict] = []
    print("虛構訓練角色對話已啟動（使用 rag_config.py 的 SYSTEM_PROMPT）")
    print("指令：/clear 清除本次對話、/quit 離開\n")

    while True:
        try:
            question = input("你：").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n已結束對話。")
            break

        if not question:
            continue
        if question.lower() in {"/quit", "/exit", "exit", "quit"}:
            print("已結束對話。")
            break
        if question.lower() == "/clear":
            history.clear()
            print("已清除本次對話歷史。\n")
            continue

        result = get_result(lambda: roleplay_rag(question, history))
        if result is None:
            continue
        show_turn(result)
        history.extend(
            [
                {"role": "user", "content": question},
                {"role": "assistant", "content": result["answer"]},
            ]
        )


if __name__ == "__main__":
    main()
