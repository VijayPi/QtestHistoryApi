import base64
import json
import logging.handlers

from com.cognizant.devops.platformagents.core.BaseAgent import BaseAgent
from dateutil import parser


class QtestAgent (BaseAgent):

    def process(self):
        try:
            # pageSize calculations from total -> pending
            baseUrl = self.config.get('baseUrl', '')
            userName = self.config.get('username', '')
            password = self.config.get('password', '')
            startFrom = self.config.get('startFrom') + '+00:00'
            startFromDate = parser.parse(startFrom, ignoretz=True)
            pageSize = self.config.get('responsePageSize', 100)
            searchUrl = '/search?page={0}&pageSize={1}'
            dynamicTemplate = self.config.get("dynamicTemplate", {})
            almEntities = dynamicTemplate.get('almEntities', {})
            metadata = dynamicTemplate.get("almEntityMetaData", None)
            idChunkSize = self.config.get('historyIdChunkSize', 10)
            isHistoryApi = self.config.get('useHistoryApi', False)
            isVersionApi = self.config.get('useVersionApi', False)
            automationType = dict()
            if isHistoryApi or isVersionApi:
                automationConfig = dynamicTemplate.get('automationType')
                automationType = automationConfig.get('test-cases')

            summaryUrl = baseUrl + "/p/{0!s}/portal/project/testdesign/testcase/history/summary?testCaseId={1!s}"
            detailUrl = baseUrl + "/p/{0!s}/portal/project/testdesign/testcase/history/detail?testCaseId={1!s}&revisionId={2!s}"
            payloadConfig = dict()
            for entityType in almEntities:
                payload = dict()
                payload['object_type'] = entityType
                payload['fields'] = ['*']
                payload['query'] = "'Last Modified Date' >= '%s'"
                payloadConfig[entityType] = json.dumps(payload)
            print payloadConfig
            encodeKey = 'InSightsAlmAgent:'
            authKey = base64.b64encode(encodeKey.encode('utf-8'))
            token = self.login(baseUrl, userName, password, authKey)
            bearerToken = 'bearer ' + token if token else None
            apiHeaders = {'Content-Type': 'application/json', 'accept': 'application/json', 'Authorization': bearerToken}
            typeHeaders = {'cookie': 'UserContextToken=' + token}
            projectData = self.getResponse(baseUrl + "/api/v3/projects?assigned=false", 'GET', None, None, None, None, apiHeaders)
            injectData = dict()
            for project in projectData:
                projectId = project.get('id', -1)
                projectIdStr = str(projectId)
                projectName = project.get('name', '')
                projectUrl = baseUrl + '/api/v3/projects/' + projectIdStr
                searchUrl = projectUrl + searchUrl
                historyUrl = projectUrl + "/histories?page={0}&pageSize={1}"
                if projectIdStr not in self.tracking:
                    self.tracking[projectIdStr] = dict()
                projectTrackingDetails = self.tracking[projectIdStr]
                injectData['projectId'] = projectId
                injectData['projectName'] = projectName
                for entity in almEntities:
                    idList = list()
                    toolsData = list()
                    responseTemplate = almEntities[entity]
                    if entity not in projectTrackingDetails:
                        lastTracked = startFrom
                        lastTrackedDate = startFromDate
                        projectTrackingDetails[entity] = dict()
                    else:
                        lastTracked = projectTrackingDetails[entity]['lastModificationDate']
                        lastTrackedDate = parser.parse(lastTracked, ignoretz=True)
                    nextResponse, page = True, 1
                    payload = payloadConfig[entity] % lastTracked
                    injectData['almType'] = entity
                    while nextResponse:
                        url = searchUrl.format(page, pageSize)
                        response = self.getResponse(url, 'POST', None, None, payload, None, apiHeaders)
                        responseData = response.get('items', None)
                        if responseData:
                            for response in responseData:
                                lastModified = response.get('last_modified_date', None)
                                lastModifiedDate = parser.parse(lastModified, ignoretz=True)
                                if lastModifiedDate > lastTrackedDate:
                                    lastTrackedDate = lastModifiedDate
                                    lastTracked = lastModified
                                responseId = response.get('id')
                                idList.append(responseId)
                                if injectData['almType'] == 'requirements':
                                    injectData['jiraKey'] = response.get('name', '').split(' ')[0]
                                for entityProperty in response.get('properties', []):
                                    injectData[str(entityProperty.get('field_name').lower()).replace(' ', '')] = entityProperty.get('field_value_name')
                                toolsData += self.parseResponse(responseTemplate, response, injectData)
                            page = page + 1
                        else:
                            nextResponse = False
                    if entity == 'test-cases' and idList:
                        automationData = list()
                        if isHistoryApi:
                            automationData = self.automationTypeHistory(historyUrl, projectId, entity, automationType, apiHeaders, idList, idChunkSize, pageSize)
                        elif isVersionApi:
                            automationData = self.automationTypeVersion(summaryUrl, detailUrl, projectId, entity, automationType, typeHeaders, idList)
                        toolsData += automationData
                    if toolsData:
                        self.publishToolsData(toolsData, metadata)
                        projectTrackingDetails[entity] = {'idList': idList, 'lastModificationDate': lastTracked}
                        self.updateTrackingJson(self.tracking)
        except Exception as err:
            logging.error(err)

    def login(self, baseUrl, userName, password, authKey):
        headers = {'accept': 'application/json', 'content-type': 'application/x-www-form-urlencoded', 'authorization': 'Basic ' + authKey}
        payload = 'grant_type=password&username=' + userName + '&password=' + password
        response = self.getResponse(baseUrl + '/oauth/token', 'POST', None, None, payload, None, headers)
        if "error" in response:
            logging.error(response)
        return response.get("access_token", None)

    def automationTypeHistory(self, historyUrl, projectId, entityType, automationType, headers, idList, idChunkSize, pageSize):
        try:
            automationData = list()
            payload = json.dumps({"object_type": entityType, "fields": ["*"], "object_query": "%s"})
            objectQueryChunks = self.constructHistoryObjectQuery(idList, idChunkSize)
            automationTimeDict = dict()
            for idChunk in objectQueryChunks:
                nextResponse = True
                page = 1
                payloadData = payload % idChunk
                while nextResponse:
                    historyResponse = dict()
                    url = historyUrl.format(page, pageSize)
                    try:
                        historyResponse = self.getResponse(url, "POST", None, None, payloadData, None, headers)
                    except Exception as err:
                        if 'response code 500' in err.message:
                            print "Hello"
                            newHistoryResponse = self.getResponse(historyUrl.format(1, 1), "POST", None, None, payloadData, None, headers)
                            print type(newHistoryResponse)
                    if 'items' in historyResponse and historyResponse['items']:
                        changeHistoryList = historyResponse.get('items')
                        for changeHistory in changeHistoryList:
                            changesList = changeHistory['changes']
                            for changedField in changesList:
                                if changedField['field'] == automationType['field'] and changedField['new_value'] == automationType['newValue']:
                                    resId = changeHistory['linked_object']['object_id']
                                    automationTime = parser.parse(changeHistory['created'], ignoretz=True)
                                    if resId not in automationTimeDict:
                                        automationTimeDict[resId] = ""
                                    automation = automationTimeDict[resId]
                                    if automation == "" or automation > automationTime:
                                        automationTimeDict[resId] = automationTime
                        page = page + 1
                    else:
                        nextResponse = False
            for key, automationTime in automationTimeDict:
                data = dict()
                data["projectId"] = projectId
                data["almType"] = entityType
                data["id"] = key,
                data["automationTimeEpoch"] = automationTime
                data["automationTime"] = automationTime.strftime(self.config.get('timeStampFormat'))
                automationData.append(data)
            return automationData

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

    def constructHistoryObjectQuery(self, idList, idChunkSize):
        if len(idList) > idChunkSize:
            objectQueryList = list()
            chunks = list()
            for responseid in range(0, len(idList), idChunkSize):
                chunks.append(idList[responseid: responseid + idChunkSize])
            for _Iter in chunks:
                objectQueryList.append(self._ConstructHistoryObjectQuery(_Iter))
            return objectQueryList
        else:
            return [self._ConstructHistoryObjectQuery(idList), ]

    def automationTypeVersion(self, summaryUrl, detailUrl, projectId, entity, automationType, headers, testCaseIds):
        automationData = list()
        automationTimeDict = dict()
        for testCaseId in testCaseIds:
            responseData = list()
            try:
                url = summaryUrl.format(projectId, testCaseId)
                responseData = self.getResponse(url, "GET", None, None, None, None, headers)
            except Exception as err:
                logging.error(err)
            resIndex = 0
            automationTimeSet = False
            while resIndex < len(responseData) and not automationTimeSet:
                response = responseData[resIndex]
                changeId = response['revisionId']
                changeResponse = list()
                try:
                    changeUrl = detailUrl.format(projectId, testCaseId, changeId)
                    changeResponse = self.getResponse(changeUrl, 'GET', None, None, None, None, headers)
                except Exception as err:
                    logging.error(err)
                automationTimeSet = False
                index = 0
                while index < len(changeResponse) and not automationTimeSet:
                    changes = changeResponse[index]
                    if changes.get('field', '') == automationType['field'] and changes.get('newValue', '') == automationType['newValue']:
                        automationTimeDict[testCaseId] = response['revisionDate'], response['revisionDateTimestamp']
                        automationTimeSet = True
                    index += 1
                resIndex = resIndex + 1
                # for changes in changeResponse:
                #     if changes.get('field', '') == automationType['field'] and changes.get('newValue', '') == automationType['newValue']:
                #         automationTimeDict[testCaseId] = response['revisionDate'], response['revisionDateTimestamp']
                #         automationTimeSet = True
                #         break
                # if automationTimeSet:
                #     break
        for testCaseId in automationData:
            data = dict()
            data['id'] = testCaseId
            data['projectId'] = projectId
            data['almType'] = entity
            data['automationTime'] = automationData[testCaseId][0]
            data['automationTimeEpoch'] = automationData[testCaseId][1]
            automationData.append(data)
        return automationData

    def logout(self, token, baseUrl):
        headerTokenRevoke = {"Authorization": "bearer "+str(token)+""}
        response = self.getResponse(baseUrl+"/oauth/revoke", 'POST', None, None, None, None, headerTokenRevoke)


if __name__ == '__main__':
    QtestAgent()
