import base64
import os
import shutil
import time

from openai import OpenAI

# utils
# =================================================================
def chat_print(label, message):
    width = shutil.get_terminal_size().columns
    msg_len = len(message)
    line_len = width - 27

    # --- normal print ---
    print(f'{time.time():.3f} {label:>6} >>> {message}')
    return

    # --- table mode ---
    if width < 38 or msg_len <= line_len:
        print(f'{time.time():.3f} {label:>6} >>> {message}')
    else:
        texts = []

        # words = message.split()
        # print(words)
        # current_line = ""
        # for word in words:
        #     if len(current_line) + len(word) + 1 <= line_len:
        #         current_line += word + " "
        #     else:
        #         texts.append(current_line)
        #         current_line = ""

        # if current_line:
        #     texts.append(current_line)

        for i in range(0, len(message), line_len):
            texts.append(message[i:i+line_len])

        for i, text in enumerate(texts):
            if i == 0:
                print(f'{time.time():.3f} {label:>6} >>> {text}')
            else:
                print(f'{"":>26} {text}')

# OpenAiHelper
# =================================================================
class OpenAiHelper():
    STT_OUT = "stt_output.wav"
    TTS_OUTPUT_FILE = 'tts_output.mp3'
    TIMEOUT = 30 # seconds

    def __init__(self, api_key, assistant_id, assistant_name, timeout=TIMEOUT, model="gpt-4o") -> None:
        self.api_key = api_key
        self.assistant_id = assistant_id
        self.assistant_name = assistant_name
        self.model = model

        self.client = OpenAI(api_key=api_key, timeout=timeout)

    def _extract_text(self, response):
        if hasattr(response, "output_text") and response.output_text:
            return response.output_text

        texts = []
        output = getattr(response, "output", []) or []
        for item in output:
            blocks = item.get("content") if isinstance(item, dict) else getattr(item, "content", [])
            for block in blocks:
                if isinstance(block, dict):
                    block_type = block.get("type")
                    text_value = block.get("text")
                else:
                    block_type = getattr(block, "type", None)
                    text_value = getattr(block, "text", None)

                if block_type in {"output_text", "text"} and text_value:
                    texts.append(text_value)

        if texts:
            return "\n".join(texts).strip()
        return ""

    def _response(self, message, image_path=None):
        if image_path:
            with open(image_path, "rb") as image_file:
                encoded = base64.b64encode(image_file.read()).decode("utf-8")
            data_url = f"data:image/jpeg;base64,{encoded}"
            payload = {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": message},
                    {"type": "input_image", "image_url": data_url},
                ],
            }
        else:
            payload = {
                "role": "user",
                "content": [{"type": "input_text", "text": message}],
            }

        return self.client.responses.create(
            model=self.model,
            input=[payload],
        )

    def stt(self, audio, language='en'):
        try:
            import wave
            from io import BytesIO

            wav_data = BytesIO(audio.get_wav_data())
            wav_data.name = self.STT_OUT

            transcript = self.client.audio.transcriptions.create(
                model="whisper-1", 
                file=wav_data,
                language=language,
                prompt="this is the conversation between me and a robot"
            )

            # file = "./stt_output.wav"
            # with wave.open(file, "wb") as wf:
            #     wf.write(audio.get_wav_data())

            # with open(file, 'rb') as f:
            #     transcript = client.audio.transcriptions.create(
            #         model="whisper-1", 
            #         file=f
            #     )
            return transcript.text
        except Exception as e:
            print(f"stt err:{e}")
            return False

    def speech_recognition_stt(self, recognizer, audio):
        import speech_recognition as sr

        # # recognize speech using Sphinx
        # try:
        #     print("Sphinx thinks you said: " + r.recognize_sphinx(audio, language="en-US"))
        # except sr.UnknownValueError:
        #     print("Sphinx could not understand audio")
        # except sr.RequestError as e:
        #     print("Sphinx error; {0}".format(e))

        # recognize speech using whisper
        # try:
        #     print("Whisper thinks you said: " + r.recognize_whisper(audio, language="english"))
        # except sr.UnknownValueError:
        #     print("Whisper could not understand audio")
        # except sr.RequestError as e:
        #     print(f"Could not request results from Whisper; {e}")

        # recognize speech using Whisper API
        try:
            return recognizer.recognize_whisper_api(audio, api_key=self.api_key)
        except sr.RequestError as e:
            print(f"Could not request results from Whisper API; {e}")
            return False

    def dialogue(self, msg):
        chat_print("user", msg)
        try:
            response = self._response(msg)
            value = self._extract_text(response)
            chat_print(self.assistant_name, value)
            try:
                return eval(value)
            except Exception:
                return str(value)
        except Exception as exc:
            print(f"dialogue err: {exc}")
            return False

    def dialogue_with_img(self, msg, img_path):
        chat_print("user", msg)
        try:
            response = self._response(msg, image_path=img_path)
            value = self._extract_text(response)
            chat_print(self.assistant_name, value)
            try:
                return eval(value)
            except Exception:
                return str(value)
        except Exception as exc:
            print(f"dialogue_with_img err: {exc}")
            return False


    def text_to_speech(self, text, output_file, voice='alloy', response_format="mp3", speed=1, instructions=''):
        '''
        voice: alloy, echo, fable, onyx, nova, and shimmer
        '''
        try:
            # check dir
            dir = os.path.dirname(output_file)
            if not os.path.exists(dir):
                os.mkdir(dir)
            elif not os.path.isdir(dir):
                raise FileExistsError(f"\'{dir}\' is not a directory")

            # tts
            with self.client.audio.speech.with_streaming_response.create(
                model="gpt-4o-mini-tts",
                voice=voice,
                input=text,
                response_format=response_format,
                speed=speed,
                instructions=instructions,
            ) as response:
                response.stream_to_file(output_file)

            return True
        except Exception as e:
            print(f'tts err: {e}')
            return False

