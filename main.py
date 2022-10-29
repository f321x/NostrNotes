import ast
import json
import time
import ssl
from nostr.event import Event, EventKind
import nostr.key
from nostr.relay_manager import RelayManager
from nostr.message_type import ClientMessageType
from nostr.key import generate_private_key, get_public_key
from nostr.filter import Filter, Filters
from kivy.app import App
from kivy.uix.label import Label
from kivy.properties import ObjectProperty, NumericProperty
from kivy.uix.textinput import TextInput
from kivy.uix.screenmanager import ScreenManager, Screen, NoTransition
import bip39

current_version = "1"

sm = ScreenManager(transition=NoTransition())
prikey = ""



try:
    keyfile = open("privkey.txt", "r")
    prikey = keyfile.read()
    keyfile.close()
except:
    keyfile = open("privkey.txt", "w")
    prikey = generate_private_key()
    keyfile.write(prikey)
    keyfile.close()

pubkey = get_public_key(prikey)

def generate_mnemonic(prikey):
    return bip39.encode_bytes(bytes.fromhex(prikey))


def decode_mnemonic(mnemonic):
    return bip39.decode_phrase(mnemonic).hex()


ss = nostr.key.compute_shared_secret(prikey, pubkey)
relay_manager = RelayManager()

relayfile = open("relays.txt", "r")
relay_list = ast.literal_eval(relayfile.read())
relayfile.close()


def nostr_connect():
    for relay in relay_list:
        if relay[0:6] == "wss://":
            relay_manager.add_relay(relay)
    relay_manager.open_connections({"cert_reqs": ssl.CERT_NONE})


def nostr_upload(notes_string):
    for tries in range(2):
        try:
            event = Event(pubkey, nostr.key.encrypt_message(notes_string, ss), kind=4, tags=[["p", pubkey]])
            event.sign(prikey)   #maybe add created_at

            message = json.dumps([ClientMessageType.EVENT, event.to_json_object()])
            relay_manager.publish_message(message)
            break
        except:
            nostr_connect()
            time.sleep(1.25)


def nostr_download():
        filters = Filters([Filter(authors=[pubkey], kinds=[EventKind.ENCRYPTED_DIRECT_MESSAGE], limit=200)])
        subscription_id = str(pubkey) + "dl"
        request = [ClientMessageType.REQUEST, subscription_id]
        request.extend(filters.to_json_array())
        for relay in relay_list:
            if relay[0:6] == "wss://":
                relay_manager.add_relay(relay)
        relay_manager.add_subscription(subscription_id, filters)
        relay_manager.open_connections({"cert_reqs": ssl.CERT_NONE})  # NOTE: This disables ssl certificate verification
        time.sleep(1.25)  # allow the connections to open

        message = json.dumps(request)
        try:
            relay_manager.publish_message(message)
        except:
            nostr_connect()
            time.sleep(1.25)
            relay_manager.publish_message(message)
        time.sleep(1)  # allow the messages to send
        event_dict = {}
        while relay_manager.message_pool.has_events():
            event_msg = relay_manager.message_pool.get_event()
            try:
                event_dict[event_msg.event.created_at] = eval(nostr.key.decrypt_message(event_msg.event.content, ss))
            except ValueError:
                pass
        if event_dict != {}:
            return event_dict[max(k for k, v in event_dict.items())]
        else:
            return None



def check_updates():
        filters = Filters([Filter(authors=["ff418ffaf56ee1e9a2de81b20b2fc3b84ff027fa7b3e2ce1fc49c5dd0ee40670"],
                                  kinds=[EventKind.TEXT_NOTE], limit=100)])
        subscription_id = str(pubkey) + "ud"
        request = [ClientMessageType.REQUEST, subscription_id]
        request.extend(filters.to_json_array())
        relay_manager.add_subscription(subscription_id, filters)

        message = json.dumps(request)
        try:
            relay_manager.publish_message(message)
            time.sleep(1)
            event_dict = {}
            while relay_manager.message_pool.has_events():
                event_msg = relay_manager.message_pool.get_event()
                event_dict[event_msg.event.created_at] = event_msg.event.content.split("/")[1]
            return event_dict[max(k for k, v in event_dict.items())]
        except:
            return current_version


note_dict = nostr_download()
if note_dict is None:
    note_dict = {}


class home(Screen):
    if note_dict != {}:
        name_id = NumericProperty(len(note_dict))
    else:
        name_id = NumericProperty(0)
    current_note = ObjectProperty()

    def add_note(self, note):
        self.name_id += 1
        self.text_inp = TextInput(text=str(note), size_hint_y=None, height=70)
        self.ids.grid_start.add_widget(self.text_inp, index=self.name_id)
        self.text_inp.bind(focus=self.update_dict)
        note_dict[self.ids.grid_start.children[self.name_id].text] = self.name_id
        sm.current = 'home'
        nostr_upload(str(note_dict))

    def update_dict(self, item, focus_bool):
        self.current_note = item
        if focus_bool:
            sm.current = 'note_edit'
            self.manager.get_screen("note_edit").ids.edit_layout.children[3].text = self.ids.grid_start.children[
                self.ids.grid_start.children.index(item)].text

    def note_delete(self):
        note_dict.pop(self.current_note.text)
        self.ids.grid_start.remove_widget(self.current_note)
        self.name_id -= 1
        sm.current = 'home'
        nostr_upload(str(note_dict))

    def update_note(self, text):
        note_dict[text] = note_dict.pop(self.current_note.text)
        self.current_note.text = text
        sm.current = 'home'
        nostr_upload(str(note_dict))


class note_create(Screen):
    def note_upload(self, note):
        self.manager.get_screen("home").add_note(note)


class note_edit(Screen):
    def update_note(self, text):
        self.manager.get_screen("home").update_note(text)


class settings(Screen):
    pass


class show_mnemonic(Screen):
    def mnemonic(self):
        mnemonic = generate_mnemonic(prikey)
        string = ""
        count = 0
        for word in mnemonic.split():
            if count % 4 == 0:
                count += 1
                string += " \n "
                string += word
                string += " "
            else:
                count += 1
                string += word
                string += " "
        return string


class restore_mnemonic(Screen):
    def restore(self, words):
        try:
            hex = decode_mnemonic(words.text)
            keyfile = open("privkey.txt", "w+")
            keyfile.write(hex)
            self.prikey = hex
            self.pubkey = get_public_key(prikey)
            keyfile.close()
            self.ids.mnemonic_words.focus = False
            self.ids.mnemonic_words.text = "Now restart the app to load your key"
        except:
            self.ids.mnemonic_words.focus = False
            self.ids.mnemonic_words.text = "Invalid words, try again"


class relays(Screen):
    relay_text = relay_list

    def update_relays(self):
        global relay_list
        self.ids.rel1.focus = False
        self.ids.rel2.focus = False
        self.ids.rel3.focus = False
        relay_list = []
        for item in self.ids:
            if item[0:4] in ['rel1', 'rel2', 'rel3']:
                if self.ids[item].text != "":
                    if self.ids[item].text[0:6] == "wss://":
                        relay_list.append(self.ids[item].text)
                    else:
                        relay_list.append("slot_not_used")
                        self.ids[item].text = "slot_not_used"
                else:
                    relay_list.append("slot_not_used")
                    self.ids[item].text = "slot_not_used"
        self.relay_text = relay_list
        relayfile = open("relays.txt", "w+")
        relayfile.write(str(relay_list))
        relayfile.close()
        sm.current = 'home'

    def abort(self):
        self.ids.rel1.focus = False
        self.ids.rel2.focus = False
        self.ids.rel3.focus = False
        count = 0
        for item in self.ids:
            if item[0:4] in ['rel1', 'rel2', 'rel3']:
                if count <= len(relay_list):
                    self.ids[item].text = relay_list[count]
                    count += 1
        sm.current = 'home'

    def clear_input(self, id):
        if self.ids[id].focus:
            self.ids[id].text = ""


class NotesApp(App):
    text_inp = ""

    def build(self):
        sm.add_widget(home(name='home'))
        sm.add_widget(note_create(name='note_create'))
        sm.add_widget(note_edit(name='note_edit'))
        sm.add_widget(settings(name='settings'))
        sm.add_widget(show_mnemonic(name="show_mnemonic"))
        sm.add_widget(restore_mnemonic(name="restore_mnemonic"))
        sm.add_widget(relays(name="relays"))
        return sm

    def on_start(self, **kwargs):
        if note_dict != {}:
            for note in note_dict:
                self.text_inp = TextInput(text=note, size_hint_y=None, height=70)
                sm.get_screen("home").ids.grid_start.add_widget(self.text_inp, index=sm.get_screen("home").name_id)
                self.text_inp.bind(focus=sm.get_screen("home").update_dict)
        newest_version = check_updates()
        if newest_version != current_version:
            if newest_version != None:
                self.update_label = Label(text="New version available on https://github.com/f321x", size_hint_y=None,
                                          height=70, color=(1, 0, 0))
                sm.get_screen("home").ids.grid_start.add_widget(self.update_label)
            else:
                self.update_label = Label(text="No or too slow internet connection", size_hint_y=None,
                                          height=70, color=(1, 0, 0))
                sm.get_screen("home").ids.grid_start.add_widget(self.update_label)

    def stop(self, *largs):
        nostr_upload(str(note_dict))
        relay_manager.close_connections()


if __name__ == '__main__':
    NotesApp().run()
