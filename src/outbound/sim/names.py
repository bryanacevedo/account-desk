FIRST = """Aaliyah Abdul Ada Adebayo Aiko Alejandro Amara Amir Ana Anders Aneesh Anika Arjun Astrid Ayesha Beatriz Benedikt
Bilal Blessing Bruno Camila Carmen Chen Chiara Chidi Clara Dalia Dario Deepa Diego Dmitri Elif Elijah Emeka Emma Esther
Fatima Felix Freya Gabriel Grace Hana Hannah Hiro Ibrahim Ines Isaac Ivy Jae Jakob Jamal Javier Jia Joao Jonas Julia
Kaito Kamala Karim Katarzyna Kemi Kenji Laila Lars Leila Leon Lucia Luis Lukas Mahmoud Malik Marco Mariana Mateo Mei
Miguel Mina Nadia Naveen Nia Nikhil Noor Olga Omar Oscar Paolo Pilar Rafael Rania Ravi Rhea Rosa Ruben Saanvi Samira
Santiago Sara Sebastian Seo-yeon Shreya Sipho Sofia Soren Tariq Thandiwe Theo Valentina Victor Wei Yara Yusuf Zara Zeynep""".split()
LAST = """Abara Adeyemi Alvarez Amari Andersson Bakker Banerjee Barros Becker Bianchi Brennan Carvalho Castillo Chaudhry Chen
Cohen Costa Dahl Delgado Diallo Dubois Eriksen Ferrari Fischer Fontaine Garcia Gupta Haddad Hansen Hartmann Hoang Ibarra
Ivanova Jansen Kapoor Kaur Kim Kowalczyk Laine Larsen Lindqvist Lopez Mahlangu Marino Mbeki Mendes Moreau Mueller Murphy
Nakamura Navarro Nguyen Novak Nwosu Okonkwo Oliveira Osei Park Patel Peeters Pereira Petrov Quinn Rahman Ramos Reddy
Richter Rossi Saito Santos Schmidt Silva Singh Sokolov Suzuki Tan Tanaka Torres Ueda Vargas Varga Vasquez Visser Wagner
Walsh Weber Wojcik Yamamoto Yilmaz Zhang Zielinski""".split()
PRE = """Arc Brightwave Cadence Cinder Clearpath Copper Corvid Crest Driftwood Ember Fathom Fernhill Flint Foxglove Glacier
Granite Harbor Heron Hollow Indigo Juniper Keystone Kestrel Larkspur Ledgerline Lumen Maple Meridian Mistral Northgate
Oakline Orbit Parallel Pebble Pinecrest Quarry Quillridge Radiant Redwood Ridgeway Saltmarsh Signal Slate Sparrow Stillwater
Summit Tidal Timber Trellis Vantage Verity Willow Zephyr""".split()
POST = """Analytics Apps Cloud Data Health Labs Logic Metrics Networks Pay Platforms Robotics Security Software Stack Systems Works""".split()
COUNTRY = {
    "US": ("North America", "America/New_York"), "CA": ("North America", "America/Toronto"),
    "GB": ("Europe", "Europe/London"), "DE": ("Europe", "Europe/Berlin"), "FR": ("Europe", "Europe/Paris"),
    "NL": ("Europe", "Europe/Amsterdam"), "ES": ("Europe", "Europe/Madrid"), "IE": ("Europe", "Europe/Dublin"),
    "BR": ("Latin America", "America/Sao_Paulo"), "AU": ("APAC", "Australia/Sydney"), "SG": ("APAC", "Asia/Singapore"),
}
US_TZ = ["America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles"]
FEMALE = set("""Aaliyah Ada Aiko Amara Ana Anika Astrid Ayesha Beatriz Camila Carmen Chiara Clara Dalia Deepa Elif Emma Esther
Fatima Freya Grace Hana Hannah Ines Ivy Jia Julia Kamala Katarzyna Kemi Laila Leila Lucia Mariana Mei Mina Nadia Nia Noor
Olga Pilar Rania Rhea Rosa Saanvi Samira Sara Seo-yeon Shreya Sofia Thandiwe Valentina Yara Zara Zeynep Blessing""".split())


class Portraits:
    """Stock portraits for the demo, from randomuser.me, handed out in turn so faces repeat as rarely as possible."""

    def __init__(self, rng) -> None:
        self.rng = rng
        self.next = {"women": rng.randrange(100), "men": rng.randrange(100)}

    def url(self, first: str) -> str | None:
        if self.rng.random() < 0.14:  # plenty of real profiles have no photo
            return None
        g = "women" if first in FEMALE else "men"
        n = self.next[g]
        self.next[g] = (n + 1) % 100
        return f"https://randomuser.me/api/portraits/{g}/{n}.jpg"
SUF = "field stone line wise path mark gate wave light craft forge peak loop grid port bridge".split()
