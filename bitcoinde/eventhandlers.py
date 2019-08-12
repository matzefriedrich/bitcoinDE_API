from bitcoinde.countries import Countries
from bitcoinde.events import BitcoinWebSocketEventHandler


class BitcoinWebSocketRemoveOrder(BitcoinWebSocketEventHandler):
    def __init__(self):
        super(BitcoinWebSocketRemoveOrder, self).__init__("rm")

    def generate_id(self, data):
        return data['id']


class BitcoinWebSocketAddOrder(BitcoinWebSocketEventHandler):
    def __init__(self):
        super(BitcoinWebSocketAddOrder, self).__init__("add")

        self.countries = Countries()

        def map_trust_level(name: str) -> int:
            levels = {
                "bronze": 1,
                "silver": 2,
                "gold": 3,
                "platinum": 4
            }
            return levels.get(name, 0)

        self.trans = {
            "id": ("id", lambda x: x),  # event-id
            "uid": ("uid", lambda x: x),
            "order_id": ("order_id", lambda x: x),
            "id": ("id", lambda x: int(x)),
            "price": ("price", lambda x: int(float(x) * 100)),
            "volume": ("volume", lambda x: int(float(x) * 100)),
            "bic_full": ("bic_full", lambda x: x),
            "only_kyc_full": ("only_kyc_full", lambda x: int(x)),
            "is_kyc_full": ("is_kyc_full", lambda x: int(x)),
            "is_trade_by_sepa_allowed": ("is_trade_by_sepa_allowed", lambda x: int(x)),
            "is_trade_by_fidor_reservation_allowed": ("is_trade_by_fidor_reservation_allowed", lambda x: int(x)),
            "amount": ("amount", lambda x: float(x)),
            "min_amount": ("min_amount", lambda x: float(x)),
            "order_type": ("order_type", lambda x: x),
            "order": ("order", lambda x: x),
            "min_trust_level": ("min_trust_level", lambda x: map_trust_level(x),),
            "seat_of_bank_of_creator": ("seat_of_bank_of_creator", lambda x: x),
            "trading_pair": ("trading_pair", lambda x: x),
            "trade_to_sepa_country": ("trade_to_sepa_country", lambda x: x),
            "fidor_account": ("fidor_account", lambda x: int(x))
        }
        # self.trans["is_shorting"]
        # self.trans["is_shorting_allowed"]

    def generate_id(self, data: dict):
        return data['id']

    def retrieve_data(self, data):
        is_shorting = int(data["is_shorting"])
        is_shorting_allowed = int(data["is_shorting_allowed"])
        short = is_shorting * 2 + is_shorting_allowed

        is_trade_by_fidor_reservation_allowed = int(data["is_trade_by_fidor_reservation_allowed"])
        is_trade_by_sepa_allowed = int(data["is_trade_by_sepa_allowed"])
        payment_option = int(data["payment_option"])
        result: dict = {
            "id": self.generate_id(data),
            "po": payment_option,
            "short": short,
            "is_trade_by_fidor_reservation_allowed": is_trade_by_fidor_reservation_allowed,
            "is_trade_by_sepa_allowed": is_trade_by_sepa_allowed
        }

        # print(is_trade_by_fidor_reservation_allowed, is_trade_by_sepa_allowed, payment_option, short)
        for key, mapping_tuple in self.trans.items():
            property_name, mapping_func, = mapping_tuple
            x = data.get(key)
            result[property_name] = mapping_func(x)

        return result


class BitcoinWebSocketSkn(BitcoinWebSocketEventHandler):
    def __init__(self):
        super(BitcoinWebSocketSkn, self).__init__("skn")

    def generate_id(self, data):
        return data['uid']


class BitcoinWebSocketSpr(BitcoinWebSocketEventHandler):

    def __init__(self):
        super(BitcoinWebSocketSpr, self).__init__("spr")

    def generate_id(data):
        return data['uid']


class BitcoinWebSocketRefreshExpressOption(BitcoinWebSocketEventHandler):
    """This event will be send in case an order´s payment options have been changed."""

    def __init__(self):
        super(BitcoinWebSocketRefreshExpressOption, self).__init__("po")

    def generate_id(self, data):
        result_id, j = 0, 1
        for key, value in data.items():  # key must be a numeric id, for instance: 58015351
            is_trade_by_fidor_reservation_allowed = int(value.get("is_trade_by_fidor_reservation_allowed", "0"))
            m = (is_trade_by_fidor_reservation_allowed * 2 - 1)
            result_id += int(key) * m * j  # wtf; would say the id remains the same...
            j += 1
        return result_id

    def retrieve_data(self, data):
        result_dict: dict = {}
        for key, value in data.items():  # items() method should return a single dict, whereby
            # key must be a numeric id, for instance: 58015351
            is_trade_by_fidor_reservation_allowed = int(value.get("is_trade_by_fidor_reservation_allowed", "0"))
            is_trade_by_sepa_allowed = int(value.get("u'is_trade_by_sepa_allowed", "0"))
            payment_option = is_trade_by_fidor_reservation_allowed + is_trade_by_sepa_allowed * 2
            result_dict["id"] = str(key)
            result_dict["po"] = payment_option
            break  # TODO: add id/po items to arrays
        return result_dict

