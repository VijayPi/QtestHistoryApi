import requests
import json
import base64
import pprint


class QueryObjectHistory:
    historyDict = dict()

    def __init__(self):
        with open('/home/vijayasekar/PycharmProjects/QtestHistoryApi/config.json', 'r') as config_file:
            self.config = json.load(config_file)
        self.baseUrl = self.config.get("baseUrl", None)
        self.username = self.config.get("username", None)
        self.password = self.config.get("password", None)
        domainName = "InSightsAlmAgent:"
        self.authToken = base64.b64encode(domainName.encode('utf-8'))
        self.token = json.loads(self.login())['access_token']
        self.queryChangeHistory = \
            self.config.get("dynamicTemplate").get("extensions").get("queryObjectHistory").get("properties")
        self._DictMapper()

    def _DictMapper(self):
        for key in self.queryChangeHistory:
            oldValue = self.queryChangeHistory[key].get('oldValue', '*Qtest*')
            newValue = self.queryChangeHistory[key].get('newValue', '*Qtest*')
            self.historyDict[key] = {oldValue: newValue} \
                if not isinstance(oldValue, list) \
                else {key: newValue for key in oldValue}

    def login(self):
        headers = {'accept': "application/json", 'content-type': "application/x-www-form-urlencoded",
                   'authorization': "Basic " + str(self.authToken) + ""}
        payload = "grant_type=password&username=" + str(self.username) + "&password=" + str(self.password)
        tokenResponse = requests.post(self.baseUrl + "/oauth/token", data=payload, headers=headers, verify=False)
        if "error" in tokenResponse:
            print("InValid Credentails")
        return tokenResponse.content

    def logout(self):
        headerTokenRevoke = {"Authorization": "bearer " + str(self.token) + ""}
        return requests.post(self.baseUrl + "/oauth/revoke", headers=headerTokenRevoke)

    def queryObjectHistoryApi(self, projectId, objectType, fields=None,
                              objectQuery=None, query=None, page=None, pageSize=None):
        headers = {'Content-Type': 'application/json', 'Authorization': 'bearer ' + self.token}
        data = {
            "object_type": objectType,
            "fields": fields if fields else ["*"],
            "object_query": objectQuery if objectQuery else "",
            "query": query if query else ""
        }
        print json.dumps(data)
        url = self.baseUrl + "/api/v3/projects/" + str(projectId) + (
            "/histories" if not page else "/histories?page={0}&page_size={1}".format(page, pageSize))
        print url
        return requests.post(url, data=json.dumps(data), headers=headers, verify=False)

    def queryEarliestchangeHistoryStrategy(self, changeHistory):
        for _iter1 in changeHistory:
            changes = _iter1['changes']
            for _iter in changes:
                field = _iter['field']
                if field in self.historyDict:
                    print _iter
                    historyField = self.historyDict[field]
                    oldValue = _iter['old_value']
                    newValue = _iter['new_value']
                    if oldValue in historyField and newValue == historyField[oldValue]:
                        print QueryObjectHistory.changeHistoryData(_iter1, field, oldValue, newValue)

    @staticmethod
    def changeHistoryData(objectHistory, changedField, fromString, toString):
        return {'id': objectHistory['id'],
                'authorId': objectHistory['author_id'],
                'created': objectHistory['created'],
                'linkedObject': objectHistory['linked_object'],
                'links': objectHistory['links'],
                'changedField': changedField,
                'fromString': fromString,
                'toString': toString}


if __name__ == "__main__":
    queryObjectHistory = QueryObjectHistory()
    print queryObjectHistory.token
    pp = pprint.PrettyPrinter(indent=3)
    changeLog = json.loads(queryObjectHistory.queryObjectHistoryApi(
        84487, "requirements", objectQuery="'id' = 9675289").content)
    queryObjectHistory.queryEarliestchangeHistoryStrategy(changeLog['items'])
    queryObjectHistory.logout()
