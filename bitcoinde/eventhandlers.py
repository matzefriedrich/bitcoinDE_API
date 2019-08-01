from bitcoinde.events import BitcoinWebSocketEventHandler


class BitcoinWebSocketRemoveOrder(BitcoinWebSocketEventHandler):
    def __init__(self):
        super(BitcoinWebSocketRemoveOrder, self).__init__("rm")

    def generate_id(self, data):
        return data['id']


class Countries(object):
    def __init__(self):
        self.codes = ["DE", "AT", "CH", "BE", "GR", "MT", "SI", "BG", "IE", "NL", "SK", "DK", "IT", "ES", "HR", "PL",
                      "CZ", "EE", "LV", "PT", "HU", "FI", "LT", "RO", "GB", "FR", "LU", "SE", "CY", "IS", "LI", "NO",
                      "MQ"]

    def decode(self, u):
        pass

    @staticmethod
    def encode(codes):
        i, j = 0, 0


class BitcoinWebSocketAddOrder(BitcoinWebSocketEventHandler):
    def __init__(self):
        super(BitcoinWebSocketAddOrder, self).__init__("add")

        self.countries = Countries()

        self.trans = {"uid": ("uid", lambda x: x),
                      "order_id": ("oid", lambda x: x),
                      "id": ("DEid", lambda x: int(x)),
                      "price": ("price", lambda x: int(float(x) * 100)),
                      "trading_pair": ("pair", lambda x: x),
                      "bic_full": ("cBIC", lambda x: x),
                      "only_kyc_full": ("rkyc", lambda x: int(x)),
                      "is_kyc_full": ("ukyc", lambda x: int(x)),
                      "amount": ("amt", lambda x: float(x)),
                      "min_amount": ("mamt", lambda x: float(x)),
                      "order_type": ("type", lambda x: x),
                      "order": ("order", lambda x: x),
                      "min_trust_level": ("trust", lambda x: {"bronze": 1,
                                                              "silver": 2,
                                                              "gold": 3,
                                                              "platinum": 4}.get(x, 0),),
                      "seat_of_bank_of_creator": ("seat", lambda x: x),
                      "trade_to_sepa_country": ("country", lambda x: x),
                      "fidor_account": ("fidor", lambda x: int(x))}
        # self.trans["is_shorting"]
        # self.trans["is_shorting_allowed"]

    @staticmethod
    def generate_id(data):
        return data['id']

    def retrieve_data(self, data):
        short = int(data["is_shorting"]) * 2 + int(data["is_shorting_allowed"])

        fidor = int(data["is_trade_by_fidor_reservation_allowed"])
        sepa = int(data["is_trade_by_sepa_allowed"])
        po = int(data["payment_option"])
        r = {"po": po, "short": short}

        print(fidor, sepa, po, short)
        for k, v in self.trans.items():
            t, f, = v
            r[t] = f(data.get(k))

        return r


class BitcoinWebSocketSkn(BitcoinWebSocketEventHandler):
    def __init__(self):
        super(BitcoinWebSocketSkn, self).__init__("skn")

    def generate_id(self, data):
        return data['uid']


class BitcoinWebSocketSpr(BitcoinWebSocketEventHandler):
    def __init__(self):
        super(BitcoinWebSocketSpr, self).__init__("spr")

    @staticmethod
    def generate_id(data):
        return data['uid']


class BitcoinWebSocketRpo(BitcoinWebSocketEventHandler):
    def __init__(self):
        super(BitcoinWebSocketRpo, self).__init__("po")

    def generate_id(self, data):
        h, j = 0, 1
        for k, v in data.items():
            m = (int(v.get("is_trade_by_fidor_reservation_allowed", "0")) * 2 - 1)
            h += int(k) * m * j
            j += 1
        return h

    def retrieve_data(self, data):
        pos = {}
        for k, v in data.items():
            fidor = int(v.get("is_trade_by_fidor_reservation_allowed", "0"))
            sepa = int(v.get("u'is_trade_by_sepa_allowed", "0"))
            po = fidor + sepa * 2
            pos[int(k)] = po
        return pos

