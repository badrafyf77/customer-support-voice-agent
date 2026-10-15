"""Small Darija syntax safeguards, separate from learned probabilities.
Overrides are deliberately limited to dangling function words and conventional
short responses. A text score cannot establish an acoustic end of turn.
"""
from core.darija_turn_text import normalize_turn_text
DANGLING={'ديال','حيت','حيث','باش','اللي','بلي','أن','بأن','بأنه','لأن','لأنو','لأنه','من','ف','في','ب','ل','إلى','إلا','يلا','حتى','بين','سواء','رغم','قبل','ولكن','و','أو','ولا'}
MODALS={'بغيت','باغي','باغية','غادي','غايكون','غتكون','يكون','تكون','كتكون','كيكون','خاصني','خاص','عند','واش','كتقول','تيقول','كنقول','نقول','نجيب','نصيفط','تصيفطو','رسل','ترسل'}
ACKS={'واخا','إييه','اييه','إيه','ايه','نعم','لا','صافي','مزيان','مرحبا','متافق','صحيح','حاضر','أكيد','اكيد','بسلامة','كلشي واضح','كلشي مزيان','واخا فهمت','صافي فهمت','سمعتك','ما فهمتش','ما سمعتكش','لا شكرا','قول ليا','لا باقي','ماشي مشكل','لا ماشي هكاك'}
def completion_override(text):
 text=normalize_turn_text(text);words=text.split()
 if not words:return 0
 if words[-1] in DANGLING:return 0
 # Standalone Arabic interrogatives can be valid questions; a trailing واش
 # after other words usually introduces a clause that is still missing.
 if len(words)>1 and words[-1] in MODALS:return 0
 if re_wait(text):return 0
 short=text
 while len(short.split())>1 and short.split()[0] in {'اه','آه','إيوا','ايوا','إييه','اييه','دابا'}:
  short=' '.join(short.split()[1:])
 if short in ACKS:return 1
 if len(words)<=8 and (short.startswith('شكرا') or short in {'السلام عليكم','وعليكم السلام','يعطيك الصحة','الله يحفظك','بارك الله فيك','شكرا على المساعدة','شكرا على التوضيح','صافي اتفقنا','إييه بالضبط'}):return 1
 return None

def re_wait(text):
 import re
 return bool(re.search(r'^(?:اه |آه |امم+ )?(?:تسنى|تسني|تسنا|تسناو|لحظة|غير لحظة|خلي نفكر|خليني نفكر|امم+|آآ+)(?: |$)',text))
