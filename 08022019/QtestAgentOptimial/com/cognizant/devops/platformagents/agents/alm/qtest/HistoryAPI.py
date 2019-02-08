import json
import logging.handlers


class HistoryApi:

    def __init__(self):
        self.entitySize = 100
        self.tc = {'newValue': 'Automation'}
        self.baseUrl = 'htt'

    def automationTypeHistory(self, entityObjectIdList, **injectData): # method name
        try:
            toolsHistoryData = list()
            projectId = injectData.get('projectId')
            entity = injectData.get('almType')
            page = 1
            pageSize = 100
            propertyLookUp = self.tc  # object var (-), entity -> t-c, process
            objectQueryChunks = self.constructHistoryObjectQuery(entityObjectIdList)
            url = self.baseUrl + "/api/v3/projects/" + str(projectId) + "/histories?page={0}&pageSize={1}"
            for idChunk in objectQueryChunks: # idChunk
                nextResponse = True
                payload = {"object_type": entity, "fields": ["*"], "object_query": idChunk}
                url = url.format(page, pageSize)
                while nextResponse:
                    historyResponse = self.getResponse(url, "POST", None, None, json.dumps(data), None, self.apiHeaders)
                    if 'items' in historyResponse and historyResponse['items']:
                        changeHistoryList = historyResponse.get('items')
                        for changeHistory in changeHistoryList:
                            changesList = changeHistory['changes']
                            for changedField in changesList:
                                if changedField['new_value'] == propertyLookUp['newValue']:
                                    data = dict()
                                    data["projectId"] = projectId
                                    data["almType"] = entity
                                    data["id"] = changeHistory['linked_object']['object_id'],
                                    data["automationTime"] = changeHistory['created']
                                    toolsHistoryData.append(data)
                        page = page + 1
                    else:
                        nextResponse = False
        except Exception as err:
            logging.error(err)

    @staticmethod
    def _ConstructHistoryObjectQuery(entityIdList):
        objectQuery = str()
        entityIdListLen = len(entityIdList)
        for index in range(0, entityIdListLen):
            entityId = entityIdList[index]
            objectQuery += '\'id\' = \'' + str(entityId) + '\''
            if index != entityIdListLen - 1:
                objectQuery += ' or '
        return objectQuery

    def constructHistoryObjectQuery(self, entityIdList):
        if len(entityIdList) > self.entitySize:
            objectQueryList = list()
            chunks = [entityIdList[_Iter: _Iter + self.entitySize] for _Iter in range(0, len(entityIdList), self.entitySize)] # expand
            for _Iter in chunks:
                objectQueryList.append(self._ConstructHistoryObjectQuery(_Iter))
            return objectQueryList
        else:
            return [self._ConstructHistoryObjectQuery(entityIdList), ]


    def queryObjectHistoryApi(self, projectId, objectType, fields=None, objectQuery=None, query=None, page=None, pageSize=None):
        pass