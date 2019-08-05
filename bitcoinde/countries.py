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
